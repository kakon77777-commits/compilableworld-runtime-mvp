from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from compilableworld.compiler import CompileError, compile_world
from compilableworld.entity_transaction import EntityTransactionRuntime
from compilableworld.gateway import DeterministicIntentParser, TerminalGateway
from compilableworld.kernel import KernelTransactionError, RuntimeErrorBase, WorldRuntime
from compilableworld.models import ActionIR
from compilableworld.modules import install_builtin_modules
from compilableworld.object_reentry import MODULE_ID, SCHEMA_ID, canonical_hash, derive
from compilableworld.schema_registry import schema_catalog, schema_contracts, schema_document
from examples.object_reentry_demo import ACTOR, OUTPUT, ROOT, TOOL, craft, open_runtime, prepare_source, run_demo


class ObjectReentryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.source = prepare_source(self.directory)
        self.package = compile_world(self.source, self.directory / "package")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def runtime_with_tool(self):
        runtime = open_runtime(self.package)
        self.assertEqual(craft(runtime).status.value, "completed")
        self.assertEqual(runtime.submit(ActionIR(ACTOR, "take", TOOL)).status.value, "completed")
        return runtime

    def observable(self, runtime):
        return deepcopy({"state": runtime.state.export(),
                         "entities": [asdict(entity) for entity in runtime.registry.values()],
                         "events": runtime.event_log.events, "scheduler": runtime.scheduler.export(),
                         "actions": runtime.actions, "metrics": dict(runtime.metrics)})

    def test_full_counterfactual_demo(self) -> None:
        result = run_demo()
        self.assertTrue(result["ok"])
        self.assertGreater(result["fresh_power"], result["worn_power"])

    def test_compiler_is_deterministic_and_preserves_source_provenance(self) -> None:
        second = compile_world(self.source, self.directory / "second")
        self.assertEqual(self.package.read_bytes(), second.read_bytes())
        package = json.loads(self.package.read_text(encoding="utf-8"))
        compiled = package["object_reentry"]
        self.assertEqual(compiled["grammar_hash"], canonical_hash(compiled["grammar"]))
        self.assertEqual(compiled["source_checksum"], package["source_checksums"]["object_reentry.json"])
        self.assertEqual(package["schema_contracts"]["object_reentry"], SCHEMA_ID)
        self.assertEqual(schema_document("object_reentry")["$id"], SCHEMA_ID)
        self.assertIn("object_reentry", {row["key"] for row in schema_catalog(include=("object_reentry",))["schemas"]})

    def test_legacy_packages_keep_their_contract_set(self) -> None:
        legacy = compile_world(ROOT / "examples" / "gray_crown", self.directory / "legacy")
        runtime = WorldRuntime.from_package(legacy)
        install_builtin_modules(runtime)
        self.assertNotIn("object_reentry", runtime.package)
        self.assertEqual(runtime.package["schema_contracts"], schema_contracts())

    def test_compiler_rejects_invalid_grammar(self) -> None:
        path = self.source / "object_reentry.json"
        original = json.loads(path.read_text(encoding="utf-8"))
        for label, mutate in {
            "version": lambda g: g.update(format="future/v99"),
            "free_guard": lambda g: g["recipes"][0].update(guard="anything"),
            "type": lambda g: g["materials"][0].update(power=True),
            "unknown_material": lambda g: g["recipes"][0].update(material_ids=["material.unknown"]),
            "duplicate": lambda g: g["materials"].append(deepcopy(g["materials"][0])),
            "depth": lambda g: g["limits"].update(max_depth=999),
            "count": lambda g: g.update(recipes=g["recipes"] * 30),
        }.items():
            with self.subTest(case=label):
                source = deepcopy(original)
                mutate(source)
                path.write_text(json.dumps(source), encoding="utf-8")
                with self.assertRaises(CompileError):
                    compile_world(self.source, self.directory / "invalid")

    def test_runtime_independently_rejects_invalid_compiled_grammar(self) -> None:
        original = json.loads(self.package.read_text(encoding="utf-8"))
        for label, mutate in {
            "hash": lambda p: p["object_reentry"]["grammar"]["materials"][0].update(power=999),
            "provenance": lambda p: p["source_checksums"].pop("object_reentry.json"),
            "schema": lambda p: p["schema_contracts"].pop("object_reentry"),
            "source_schema": lambda p: p["manifest"]["source_schemas"].pop("object_reentry"),
            "missing_source": lambda p: p.pop("object_reentry"),
            "missing_module": lambda p: p["manifest"]["modules"].remove(MODULE_ID),
            "version": lambda p: p["object_reentry"].update(format="future/v99"),
        }.items():
            with self.subTest(case=label):
                payload = deepcopy(original)
                mutate(payload)
                bad = self.directory / "bad.package.json"
                bad.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaises(RuntimeErrorBase):
                    EntityTransactionRuntime.from_package(bad)

    def test_recomputed_hash_does_not_bypass_runtime_semantic_validation(self) -> None:
        original = json.loads(self.package.read_text(encoding="utf-8"))
        for label, mutate, reason in (
            ("depth", lambda g: g["limits"].update(max_depth=9), "max_depth"),
            ("reference", lambda g: g["recipes"][0].update(material_ids=["material.missing"]), "material references"),
            ("type", lambda g: g["materials"][0].update(power=True), "material.power"),
        ):
            with self.subTest(case=label):
                payload = deepcopy(original)
                compiled = payload["object_reentry"]
                mutate(compiled["grammar"])
                compiled["grammar_hash"] = canonical_hash(compiled["grammar"])
                bad = self.directory / "semantic.package.json"
                bad.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaisesRegex(RuntimeErrorBase, reason):
                    EntityTransactionRuntime.from_package(bad)

    def test_generation_module_requires_entity_transaction_runtime(self) -> None:
        selected = WorldRuntime.from_package(self.package)
        self.assertIsInstance(selected, EntityTransactionRuntime)
        runtime = WorldRuntime(selected.package)
        with self.assertRaisesRegex(ValueError, "EntityTransactionRuntime"):
            install_builtin_modules(runtime)
        self.assertEqual(runtime.modules, {})

    def test_normal_gateway_routes_crafting_through_action_ir(self) -> None:
        runtime = WorldRuntime.from_package(self.package)
        install_builtin_modules(runtime)
        parser = DeterministicIntentParser()
        for command in (
            f"craft workshop.make_tool material.iron - 7 {TOOL}",
            f"take {TOOL}", f"use_tool {TOOL}",
            f"craft workshop.make_blade material.iron {TOOL} 23 {OUTPUT}",
        ):
            self.assertEqual(runtime.submit(parser.parse(command, ACTOR, runtime)).status.value, "completed")
        self.assertTrue(runtime.registry.contains(OUTPUT))
        self.assertIn("craft 配方ID", TerminalGateway(runtime, ACTOR)._help_text())
        for command in ("craft", "craft recipe material - bad-seed", "use_tool"):
            with self.assertRaises(ValueError):
                parser.parse(command, ACTOR, runtime)

    def test_seeded_preview_and_visual_recipe_are_read_only(self) -> None:
        runtime = self.runtime_with_tool()
        module = runtime.modules[MODULE_ID]
        before = self.observable(runtime)
        first = module.preview(runtime, ACTOR, "workshop.make_blade", "material.iron", 23, TOOL)
        second = module.preview(runtime, ACTOR, "workshop.make_blade", "material.iron", 23, TOOL)
        self.assertEqual(first, second)
        self.assertLessEqual(first["bonus"], 3)
        self.assertTrue(module.visual_recipe(runtime, TOOL)["read_only"])
        self.assertEqual(self.observable(runtime), before)

    def test_seed_algorithm_has_fixed_cross_version_vectors(self) -> None:
        grammar = open_runtime(self.package).modules[MODULE_ID].grammar
        self.assertEqual(canonical_hash(grammar), "a867763e56f75a1597ffc3f244f396139794183fef2c17a83a6e72c6e8f0ca94")
        for seed, bonus in ((0, 2), (7, 1), (23, 2), (4294967295, 0)):
            with self.subTest(seed=seed):
                result = derive(grammar, "workshop.make_tool", "material.iron", seed)
                self.assertEqual(result["algorithm"], "sha256-prefix64-mod/v1")
                self.assertEqual(result["bonus"], bonus)
                self.assertEqual(result["output_power"], 28 + bonus)

    def test_history_and_state_revisions_enter_the_next_recipe(self) -> None:
        runtime = self.runtime_with_tool()
        self.assertEqual(runtime.submit(ActionIR(ACTOR, "use_tool", TOOL)).status.value, "completed")
        last_event = runtime.state.get(TOOL, "craft", "last_event_id")
        version = runtime.state.version(TOOL, "craft", "condition")
        self.assertEqual(craft(runtime, "workshop.make_blade", output=OUTPUT, tool=TOOL).status.value, "completed")
        record = runtime.registry.get(OUTPUT).metadata["object_reentry"]
        self.assertEqual(record["input_tool"]["condition"], 75)
        self.assertEqual(record["input_tool"]["last_event_id"], last_event)
        self.assertEqual(record["input_tool"]["versions"]["condition"], version)
        self.assertEqual(runtime.state.get(TOOL, "craft", "condition"), 50)
        self.assertIn(last_event, [e.event_id for e in runtime.event_log.events if e.event_type == "craft.used"])

    def test_counterfactual_oracle_catches_a_generator_ignoring_condition(self) -> None:
        def ignore_condition(grammar, recipe_id, material_id, seed, tool=None):
            if tool is not None:
                tool = deepcopy(tool)
                tool["condition"] = 100
            return derive(grammar, recipe_id, material_id, seed, tool)
        with patch("compilableworld.object_reentry_module.derive", side_effect=ignore_condition):
            with self.assertRaisesRegex(AssertionError, "condition feedback"):
                run_demo()

    def test_failed_creation_and_log_append_do_not_consume_tool_condition(self) -> None:
        runtime = self.runtime_with_tool()
        before = runtime.state.export()
        self.assertEqual(craft(runtime, "workshop.make_blade", output=TOOL, tool=TOOL).status.value, "failed")
        self.assertEqual(runtime.state.export(), before)
        before_events = list(runtime.event_log.events)
        with patch.object(runtime.event_log, "append_batch", side_effect=KernelTransactionError("disk failed")):
            with self.assertRaises(KernelTransactionError):
                craft(runtime, "workshop.make_blade", output=OUTPUT, tool=TOOL)
        self.assertEqual(runtime.state.export(), before)
        self.assertFalse(runtime.registry.contains(OUTPUT))
        self.assertEqual(runtime.event_log.events, before_events)

    def test_invalid_actions_are_rejected_before_world_changes(self) -> None:
        runtime = self.runtime_with_tool()
        for action in (
            ActionIR(ACTOR, "craft", TOOL, {"recipe_id": "workshop.make_blade", "material_id": "material.iron", "seed": True}),
            ActionIR(ACTOR, "craft", None, {"recipe_id": "workshop.make_blade", "material_id": "material.iron", "seed": 1}),
            ActionIR(ACTOR, "craft", TOOL, {"recipe_id": "workshop.reforge_tool", "material_id": "material.bronze", "seed": 1}),
            ActionIR(ACTOR, "use_tool", TOOL, {"condition": 100}),
        ):
            before = runtime.state.export()
            self.assertEqual(runtime.submit(action).status.value, "failed")
            self.assertEqual(runtime.state.export(), before)

    def test_tool_must_be_carried_and_have_the_correct_kind(self) -> None:
        runtime = open_runtime(self.package)
        craft(runtime)
        self.assertEqual(craft(runtime, "workshop.make_blade", output=OUTPUT, tool=TOOL).status.value, "failed")
        runtime.submit(ActionIR(ACTOR, "take", TOOL))
        craft(runtime, "workshop.make_blade", output=OUTPUT, tool=TOOL)
        runtime.submit(ActionIR(ACTOR, "take", OUTPUT))
        self.assertEqual(craft(runtime, "workshop.make_blade", output="item.invalid", tool=OUTPUT).status.value, "failed")

    def test_boolean_recipe_depth_does_not_alias_integer_depth(self) -> None:
        runtime = self.runtime_with_tool()
        runtime.registry.get(TOOL).metadata["object_reentry"]["depth"] = True
        before = runtime.state.export()
        self.assertEqual(runtime.submit(ActionIR(ACTOR, "use_tool", TOOL)).status.value, "failed")
        self.assertEqual(runtime.state.export(), before)

    def test_wear_and_recursive_depth_have_explicit_limits(self) -> None:
        runtime = self.runtime_with_tool()
        for _ in range(4):
            self.assertEqual(runtime.submit(ActionIR(ACTOR, "use_tool", TOOL)).status.value, "completed")
        self.assertEqual(runtime.state.get(TOOL, "craft", "condition"), 0)
        self.assertEqual(craft(runtime, "workshop.make_blade", output=OUTPUT, tool=TOOL).status.value, "failed")
        runtime = self.runtime_with_tool()
        parent = TOOL
        for depth in (2, 3):
            child = f"item.depth_{depth}"
            self.assertEqual(craft(runtime, "workshop.reforge_tool", output=child, tool=parent).status.value, "completed")
            self.assertEqual(runtime.submit(ActionIR(ACTOR, "take", child)).status.value, "completed")
            self.assertEqual(runtime.state.get(child, "craft", "depth"), depth)
            parent = child
        before = runtime.state.export()
        self.assertEqual(craft(runtime, "workshop.reforge_tool", output="item.too_deep", tool=parent).status.value, "failed")
        self.assertEqual(runtime.state.export(), before)

    def test_omitted_seed_and_id_are_recorded_but_bounded(self) -> None:
        runtime = open_runtime(self.package)
        receipt = runtime.submit(ActionIR(ACTOR, "craft", args={
            "recipe_id": "workshop.make_tool", "material_id": "material.iron",
        }))
        self.assertEqual(receipt.status.value, "completed")
        record = runtime.registry.get(receipt.changed_entities[0]).metadata["object_reentry"]
        self.assertGreaterEqual(record["seed"], 0)
        self.assertLessEqual(record["seed"], 2**32 - 1)
        self.assertEqual(derive(runtime.modules[MODULE_ID].grammar, record["recipe_id"], record["material_id"], record["seed"]), record)


if __name__ == "__main__":
    unittest.main()
