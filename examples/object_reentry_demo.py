"""Fixed-grammar, offline history feedback witness. Run with PYTHONPATH=src."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory

from compilableworld.compiler import compile_world
from compilableworld.entity_transaction import EntityTransactionRuntime
from compilableworld.models import ActionIR
from compilableworld.modules import install_builtin_modules
from compilableworld.object_reentry import MODULE_ID, SCHEMA_ID


ROOT = Path(__file__).resolve().parents[1]
ACTOR = "player.neo"
TOOL = "item.reentry_tool"
OUTPUT = "item.reentry_blade"


def prepare_source(directory: Path) -> Path:
    """Create an isolated authoring fixture; never edit the base example."""
    source = directory / "source"
    shutil.copytree(ROOT / "examples" / "gray_crown", source)
    shutil.copyfile(ROOT / "examples" / "object_reentry_catalog.json", source / "object_reentry.json")
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    manifest["sources"]["object_reentry"] = "object_reentry.json"
    manifest["source_schemas"]["object_reentry"] = SCHEMA_ID
    manifest["modules"].append(MODULE_ID)
    (source / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return source


def open_runtime(package: Path, log: Path | None = None) -> EntityTransactionRuntime:
    runtime = EntityTransactionRuntime.from_package(package, log)
    install_builtin_modules(runtime)
    return runtime


def craft(runtime, recipe="workshop.make_tool", *, output=TOOL, tool=None, seed=7, material="material.iron"):
    return runtime.submit(ActionIR(ACTOR, "craft", tool, {
        "recipe_id": recipe, "material_id": material, "seed": seed, "output_id": output,
    }))


def run_demo() -> dict:
    with TemporaryDirectory(prefix="cw-object-reentry-") as temp:
        directory = Path(temp)
        package = compile_world(prepare_source(directory), directory / "package")
        log = directory / "world.jsonl"
        runtime = open_runtime(package, log)
        assert craft(runtime).status.value == "completed"
        assert runtime.submit(ActionIR(ACTOR, "take", TOOL)).status.value == "completed"
        pristine = directory / "pristine.json"
        runtime.save_snapshot(pristine)

        assert craft(runtime, "workshop.make_blade", output=OUTPUT, tool=TOOL, seed=23).status.value == "completed"
        fresh_power = runtime.state.get(OUTPUT, "craft", "power")
        runtime.load_snapshot(pristine)
        assert runtime.submit(ActionIR(ACTOR, "use_tool", TOOL)).status.value == "completed"
        history_event = runtime.state.get(TOOL, "craft", "last_event_id")
        worn_checkpoint = directory / "worn.json"
        runtime.save_snapshot(worn_checkpoint)
        assert craft(runtime, "workshop.make_blade", output=OUTPUT, tool=TOOL, seed=23).status.value == "completed"
        worn_power = runtime.state.get(OUTPUT, "craft", "power")
        assert fresh_power > worn_power, "condition feedback must change gameplay power"
        recipe = runtime.registry.get(OUTPUT).metadata["object_reentry"]
        assert recipe["input_tool"]["last_event_id"] == history_event

        restored = open_runtime(package)
        restored.load_snapshot(worn_checkpoint)
        assert craft(restored, "workshop.make_blade", output=OUTPUT, tool=TOOL, seed=23).status.value == "completed"
        assert restored.registry.get(OUTPUT).metadata["object_reentry"] == recipe

        replayed = open_runtime(package, log)
        before_log = log.read_bytes()
        replayed.replay(replayed.event_log.events)
        assert log.read_bytes() == before_log
        assert replayed.state.export() == runtime.state.export()
        assert replayed.registry.get(OUTPUT) == runtime.registry.get(OUTPUT)
        module = replayed.modules[MODULE_ID]
        before = deepcopy(replayed.state.export())
        visual = module.visual_recipe(replayed, OUTPUT)
        assert replayed.state.export() == before
        assert craft(replayed, "workshop.make_blade", output="item.continued", tool=TOOL, seed=23).status.value == "completed"
        again = open_runtime(package, log)
        again.replay(again.event_log.events)
        assert again.state.export() == replayed.state.export()
        return {
            "ok": True, "same_seed": 23, "fresh_tool_condition": 100, "worn_tool_condition": 75,
            "fresh_power": fresh_power, "worn_power": worn_power,
            "history_reference_retained": True, "snapshot_next_generation": "matched",
            "replay_and_continued_generation": "matched", "visual_recipe": visual,
        }


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(run_demo(), ensure_ascii=False, indent=2))
