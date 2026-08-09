from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from compilableworld.compiler import compile_world
from compilableworld.kernel import ActionIR, WorldRuntime
from compilableworld.modules import install_builtin_modules
from compilableworld.studio import (
    STUDIO_FUNCTION_PREVIEW_FORMAT,
    STUDIO_OVERVIEW_FORMAT,
    function_catalog,
    function_preview,
    package_overview,
    runtime_overview,
)


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "mingyun_zhiyu_peace_city"


class StudioOverviewTests(unittest.TestCase):
    def test_package_overview_projects_fms_tms_and_quest_graph(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            package_path = compile_world(EXAMPLE, temp)
            package = json.loads(package_path.read_text(encoding="utf-8"))
            overview = package_overview(package)

        self.assertEqual(overview["format"], STUDIO_OVERVIEW_FORMAT)
        self.assertEqual(overview["planes"]["fms"]["world_id"], "mingyun_zhiyu_peace_city_slice")
        self.assertIn("quest.core", overview["planes"]["tms"]["declared_modules"])
        self.assertGreaterEqual(overview["entities"]["total"], 1)
        self.assertIn("dialogue.responded", overview["events"]["declared"])
        quest = next(item for item in overview["quests"] if item["quest_id"] == "quest.find_work")
        self.assertIn("completed", quest["states"])
        self.assertEqual(overview["diagnostics"]["errors"], 0)

    def test_package_overview_surfaces_unreachable_states_as_diagnostics(self) -> None:
        package = {
            "format": "compilableworld.runtime-package/v0.1",
            "manifest": {"world_id": "demo", "world_version": "0.1.0", "schema_version": "0.1.0", "namespace": "demo", "modules": []},
            "world": {},
            "entities": [],
            "initial_state": [],
            "quests": [{
                "quest_id": "quest.demo",
                "title": "Demo",
                "initial_state": "idle",
                "transitions": [{"transition_id": "transition.demo", "from": "orphan", "on": "event.demo", "to": "done", "priority": 0}],
            }],
        }
        overview = package_overview(package)
        codes = {issue["code"] for issue in overview["diagnostics"]["issues"]}
        self.assertIn("unreachable_state", codes)
        self.assertIn("orphan", next(iter(overview["quests"]))["states"])

    def test_package_overview_projects_semantic_records_as_read_only_metadata(self) -> None:
        package = {
            "format": "compilableworld.runtime-package/v0.1",
            "manifest": {"world_id": "demo", "world_version": "0.1.0", "schema_version": "0.1.0", "namespace": "demo", "modules": []},
            "world": {},
            "entities": [],
            "initial_state": [],
            "quests": [],
            "studio": {
                "semantic_records_are_metadata_only": True,
                "semantic_records_format": "compilableworld.studio-semantic-records/v0.1",
                "semantic_records": {
                    "quest.demo": {
                        "responses": [{"id": "response.demo", "text": "A reviewed response."}],
                    },
                },
            },
        }
        overview = package_overview(package)

        self.assertTrue(overview["semantic_records"]["metadata_only"])
        self.assertEqual(
            overview["semantic_records"]["state_machines"]["quest.demo"]["responses"][0]["id"],
            "response.demo",
        )
        overview["semantic_records"]["state_machines"]["quest.demo"]["responses"][0]["id"] = "changed"
        self.assertEqual(
            package["studio"]["semantic_records"]["quest.demo"]["responses"][0]["id"],
            "response.demo",
        )

    def test_runtime_overview_contains_module_contracts_and_trace_tail(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            runtime = WorldRuntime.from_package(compile_world(EXAMPLE, temp))
            install_builtin_modules(runtime)
            runtime.submit(ActionIR("player.newcomer", "look"))
            runtime.functions.evaluate("math.clamp", {"value": 12, "minimum": 0, "maximum": 10})
            runtime.functions.evaluate("math.clamp", {"value": 12, "minimum": 0, "maximum": 10})
            overview = runtime_overview(runtime)

        self.assertIn("room.core", overview["runtime"]["modules"])
        self.assertTrue(overview["runtime"]["trace_tail"])
        self.assertEqual(overview["runtime"]["trace_tail"][0]["event_type"], "state.committed")
        self.assertEqual(overview["runtime"]["diagnostics"]["function_cache"]["hits"], 1)

    def test_function_catalog_and_preview_are_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            runtime = WorldRuntime.from_package(compile_world(EXAMPLE, temp))
            before = runtime.state.export()
            catalog = function_catalog(runtime.package)
            preview = function_preview(runtime, "combat.damage", {"ar_effective": 1134.9, "dr": 606.8})
            after = runtime.state.export()

        self.assertEqual(catalog["format"], "compilableworld.function-catalog/v0.1")
        self.assertTrue(catalog["read_only"])
        self.assertIn("combat.damage", [item["function_id"] for item in catalog["functions"]])
        self.assertEqual(preview["format"], STUDIO_FUNCTION_PREVIEW_FORMAT)
        self.assertTrue(preview["read_only"])
        self.assertEqual(preview["result"], 83)
        self.assertEqual(before, after)
