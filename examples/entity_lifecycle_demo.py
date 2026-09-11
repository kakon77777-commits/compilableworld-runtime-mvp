"""Offline create -> save -> replay -> continue demo using a compiled world.

Run from the repository with PYTHONPATH=src:
    python -B examples/entity_lifecycle_demo.py
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from compilableworld.compiler import compile_world
from compilableworld.entity_transaction import ENTITY_TRANSACTION_CAPABILITY, EntityTransactionRuntime
from compilableworld.models import ActionIR, Entity, EntityDelta, EventIR, ModuleContract, StateDelta, TransitionResult
from compilableworld.modules import install_builtin_modules


ACTOR = "player.neo"
ITEM = "item.day02_keepsake"


class KeepsakeModule:
    """Synthetic example capability, not a new canonical world rule."""

    contract = ModuleContract(
        module_id="demo.keepsake", version="0.1.0", layer="runtime",
        actions=["make_keepsake"], events=["keepsake.created"],
        read=["position.*"], write=["position.*", "inventory.*", "lineage.*"],
        requires_kernel=[ENTITY_TRANSACTION_CAPABILITY],
    )

    def evaluate(self, action: ActionIR, runtime: EntityTransactionRuntime) -> TransitionResult:
        entity_id = action.args.get("item_id", ITEM)
        entity = Entity(
            entity_id, "item", "重啟紀念牌", ["position", "inventory"],
            {"provenance": "synthetic_day02_demo", "portable": True, "recipe": {
                "template": "day02.keepsake/v0.1", "creator": action.actor_id,
            }},
        )
        return TransitionResult(
            accepted=True,
            deltas=[
                StateDelta(entity_id, "position", "room", "set",
                           runtime.state.get(action.actor_id, "position", "room")),
                StateDelta(entity_id, "inventory", "carrier", "set", None),
                StateDelta(entity_id, "lineage", "creator", "set", action.actor_id),
                StateDelta(entity_id, "lineage", "created_tick", "set", runtime.scheduler.tick),
            ],
            events=[EventIR("keepsake.created", self.contract.module_id, {"entity_id": entity_id})],
            message="紀念牌已建立",
            entity_deltas=[EntityDelta("create", entity, source_module=self.contract.module_id)],
        )


def open_runtime(package: Path, event_log: Path | None = None) -> EntityTransactionRuntime:
    runtime = EntityTransactionRuntime.from_package(package, event_log)
    install_builtin_modules(runtime)
    runtime.register_module(KeepsakeModule())
    return runtime


def run_demo() -> dict:
    root = Path(__file__).resolve().parents[1]
    with TemporaryDirectory(prefix="cw-entity-lifecycle-") as temp:
        directory = Path(temp)
        package = compile_world(root / "examples" / "gray_crown", directory / "package")
        log_path = directory / "events.jsonl"
        snapshot = directory / "checkpoint.json"
        runtime = open_runtime(package, log_path)
        assert runtime.submit(ActionIR(ACTOR, "make_keepsake")).status.value == "completed"
        runtime.save_snapshot(snapshot)
        assert runtime.submit(ActionIR(ACTOR, "take", ITEM)).status.value == "completed"

        restored = open_runtime(package)
        restored.load_snapshot(snapshot)
        assert restored.registry.get(ITEM) == runtime.registry.get(ITEM)
        assert restored.state.get(ITEM, "inventory", "carrier") is None
        assert restored.submit(ActionIR(ACTOR, "take", ITEM)).status.value == "completed"

        restarted = open_runtime(package, log_path)
        log_before = log_path.read_bytes()
        restarted.replay(restarted.event_log.events)
        assert log_path.read_bytes() == log_before
        assert restarted.state.export() == runtime.state.export()
        assert restarted.registry.get(ITEM) == runtime.registry.get(ITEM)
        assert restarted.submit(ActionIR(ACTOR, "drop", ITEM)).status.value == "completed"

        second_restart = open_runtime(package, log_path)
        second_restart.replay(second_restart.event_log.events)
        assert second_restart.state.export() == restarted.state.export()
        assert second_restart.registry.get(ITEM).metadata["recipe"]["creator"] == ACTOR
        return {
            "ok": True, "entity_id": ITEM, "snapshot_format": "compilableworld.snapshot/v0.6",
            "snapshot_restore_and_action": "passed", "replay_and_two_restarts": "passed",
            "lineage_creator": second_restart.state.get(ITEM, "lineage", "creator"),
            "final_carrier": second_restart.state.get(ITEM, "inventory", "carrier"),
            "events": len(second_restart.event_log.events),
        }


if __name__ == "__main__":
    print(json.dumps(run_demo(), ensure_ascii=False, indent=2))
