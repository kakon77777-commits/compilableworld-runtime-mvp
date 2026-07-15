from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from compilableworld.compiler import CompileError, compile_world
from compilableworld.scenarios import run_scenario


ROOT = Path(__file__).resolve().parents[1]
GRAY_CROWN = ROOT / "examples" / "gray_crown"
PEACE_CITY = ROOT / "examples" / "mingyun_zhiyu_peace_city"


class ScenarioIRTests(unittest.TestCase):
    def test_compiler_packages_authored_scenarios(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            package_path = compile_world(PEACE_CITY, temp)
            package = json.loads(package_path.read_text(encoding="utf-8"))
        self.assertEqual(package["scenarios"]["scenarios"][0]["scenario_id"], "peace_city.find_work")

    def test_peace_city_scenario_runs_through_normal_runtime_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            package = json.loads(compile_world(PEACE_CITY, temp).read_text(encoding="utf-8"))
            report = run_scenario(package, "peace_city.find_work")
        self.assertTrue(report["passed"], report)
        self.assertIn("quest.completed", report["observed_event_types"])

    def test_gray_crown_scenario_runs_through_normal_runtime_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            package = json.loads(compile_world(GRAY_CROWN, temp).read_text(encoding="utf-8"))
            report = run_scenario(package, "gray_crown.open_vault")
        self.assertTrue(report["passed"], report)
        self.assertEqual(report["actor_id"], "player.neo")

    def test_unknown_scenario_target_fails_at_compile_time(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            world = Path(temp) / "world"
            shutil.copytree(PEACE_CITY, world)
            scenarios_path = world / "scenarios.json"
            scenarios = json.loads(scenarios_path.read_text(encoding="utf-8"))
            scenarios["scenarios"][0]["when"][0]["target_id"] = "npc.not_real"
            scenarios_path.write_text(json.dumps(scenarios), encoding="utf-8")
            with self.assertRaisesRegex(CompileError, "target_id"):
                compile_world(world, Path(temp) / "out")


if __name__ == "__main__":
    unittest.main()
