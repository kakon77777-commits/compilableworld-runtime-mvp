from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from compilableworld.compiler import CompileError, compile_world
from compilableworld.functions import FunctionRegistry, FunctionRegistryError
from compilableworld.kernel import WorldRuntime
from compilableworld.studio import package_overview


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "mingyun_zhiyu_peace_city"


class FunctionRegistryTests(unittest.TestCase):
    def test_compiled_functions_are_available_to_runtime_and_studio(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            package_path = compile_world(EXAMPLE, temp)
            package = json.loads(package_path.read_text(encoding="utf-8"))
            runtime = WorldRuntime.from_package(package_path)
            overview = package_overview(package)

        self.assertEqual(overview["functions"]["count"], 11)
        self.assertEqual(overview["functions"]["ids"], [
            "combat.action_economy",
            "combat.damage",
            "combat.hit_chance",
            "combat.hp_from_con",
            "combat.initiative_value",
            "combat.melee_ar",
            "combat.melee_dr",
            "math.clamp",
            "player.attribute_from_weight",
            "player.fp_from_mag_dex",
            "player.mp_from_mag",
        ])
        self.assertEqual(runtime.functions.evaluate("math.clamp", {"value": 12, "minimum": 0, "maximum": 10}), 10)
        self.assertEqual(runtime.functions.evaluate("math.clamp", {"value": -2, "minimum": 0, "maximum": 10}), 0)
        self.assertEqual(runtime.functions.evaluate("combat.hp_from_con", {"con": 12}), 96)

    def test_function_inputs_are_exact_and_numeric(self) -> None:
        registry = FunctionRegistry({"functions": [{
            "function_id": "math.double",
            "version": "0.1.0",
            "purity": "pure",
            "inputs": {"value": "number"},
            "output": "number",
            "expression": {"op": "mul", "args": [{"ref": "value"}, 2]},
        }]})

        with self.assertRaises(FunctionRegistryError):
            registry.evaluate("math.double", {})
        with self.assertRaises(FunctionRegistryError):
            registry.evaluate("math.double", {"value": True})

    def test_function_registry_uses_bounded_lru_memoization(self) -> None:
        registry = FunctionRegistry({"functions": [{
            "function_id": "math.double",
            "version": "0.1.0",
            "purity": "pure",
            "inputs": {"value": "number"},
            "output": "number",
            "expression": {"op": "mul", "args": [{"ref": "value"}, 2]},
        }]}, max_cache_entries=1)

        self.assertEqual(registry.evaluate("math.double", {"value": 4}), 8)
        self.assertEqual(registry.evaluate("math.double", {"value": 4}), 8)
        self.assertEqual(registry.cache_stats(), {"hits": 1, "misses": 1, "evictions": 0, "size": 1, "capacity": 1})

        registry.evaluate("math.double", {"value": 5})
        self.assertEqual(registry.cache_stats()["evictions"], 1)
        registry.evaluate("math.double", {"value": 4})
        self.assertEqual(registry.cache_stats()["misses"], 3)

        registry.clear_cache()
        self.assertEqual(registry.cache_stats(), {"hits": 0, "misses": 0, "evictions": 0, "size": 0, "capacity": 1})

    def test_compile_rejects_unsupported_function_operation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "world"
            shutil.copytree(EXAMPLE, source)
            functions_path = source / "functions.json"
            functions = json.loads(functions_path.read_text(encoding="utf-8"))
            functions["functions"][0]["expression"]["op"] = "python"
            functions_path.write_text(json.dumps(functions), encoding="utf-8")

            with self.assertRaisesRegex(CompileError, "functions.json invalid"):
                compile_world(source, Path(temp) / "build")


if __name__ == "__main__":
    unittest.main()
