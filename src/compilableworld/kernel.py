from __future__ import annotations

import fnmatch
import heapq
import json
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Iterable, Protocol

from .models import (
    ActionIR, ActionReceipt, ActionStatus, Entity, EventIR, ModuleContract,
    StateCell, StateDelta, TransitionResult, new_id,
)


class RuntimeErrorBase(RuntimeError):
    pass


class ConflictError(RuntimeErrorBase):
    pass


class PermissionDenied(RuntimeErrorBase):
    pass


class EntityRegistry:
    def __init__(self) -> None:
        self._entities: dict[str, Entity] = {}

    def add(self, entity: Entity) -> None:
        if entity.entity_id in self._entities:
            raise RuntimeErrorBase(f"重複實體: {entity.entity_id}")
        self._entities[entity.entity_id] = entity

    def get(self, entity_id: str) -> Entity:
        try:
            return self._entities[entity_id]
        except KeyError as exc:
            raise RuntimeErrorBase(f"未知實體: {entity_id}") from exc

    def contains(self, entity_id: str) -> bool:
        return entity_id in self._entities

    def values(self) -> Iterable[Entity]:
        return self._entities.values()


class StateStore:
    def __init__(self) -> None:
        self._cells: dict[str, StateCell] = {}

    @staticmethod
    def path(owner: str, namespace: str, key: str) -> str:
        # Authoring IDs may contain dots; a double-colon separator keeps paths reversible.
        return f"{owner}::{namespace}::{key}"

    def seed(self, owner: str, namespace: str, key: str, value: Any, version: int = 0) -> None:
        self._cells[self.path(owner, namespace, key)] = StateCell(value, version)

    def get(self, owner: str, namespace: str, key: str, default: Any = None) -> Any:
        cell = self._cells.get(self.path(owner, namespace, key))
        return default if cell is None else cell.value

    def version(self, owner: str, namespace: str, key: str) -> int:
        cell = self._cells.get(self.path(owner, namespace, key))
        return -1 if cell is None else cell.version

    def commit(self, deltas: list[StateDelta], allowed_write: list[str]) -> list[dict[str, Any]]:
        pending: dict[str, Any] = {}
        versions: dict[str, int] = {}
        for delta in deltas:
            logical_path = f"{delta.namespace}.{delta.key}"
            if not any(fnmatch.fnmatch(logical_path, pattern) for pattern in allowed_write):
                raise PermissionDenied(f"模組不可寫入 {logical_path}")
            cell = self._cells.get(delta.path, StateCell(None, -1))
            current_value = pending.get(delta.path, cell.value)
            current_version = versions.get(delta.path, cell.version)
            if delta.expected_version is not None and delta.expected_version != current_version:
                raise ConflictError(
                    f"{delta.path} 版本衝突: expected={delta.expected_version}, actual={current_version}"
                )
            pending[delta.path] = self._apply(current_value, delta.operation, delta.value)
            versions[delta.path] = current_version + 1
        applied: list[dict[str, Any]] = []
        for path, value in pending.items():
            self._cells[path] = StateCell(value, versions[path])
            delta = next(item for item in reversed(deltas) if item.path == path)
            applied.append({
                "path": path,
                "owner": delta.owner,
                "namespace": delta.namespace,
                "key": delta.key,
                "value": value,
                "version": versions[path],
            })
        return applied

    @staticmethod
    def _apply(current: Any, operation: str, value: Any) -> Any:
        if operation == "set":
            return value
        if operation == "add":
            return (current or 0) + value
        if operation == "subtract":
            return (current or 0) - value
        if operation == "append":
            return list(current or []) + [value]
        if operation == "remove":
            result = list(current or [])
            if value in result:
                result.remove(value)
            return result
        raise RuntimeErrorBase(f"未知 Delta operation: {operation}")

    def export(self) -> dict[str, dict[str, Any]]:
        return {path: asdict(cell) for path, cell in sorted(self._cells.items())}

    def import_state(self, data: dict[str, dict[str, Any]]) -> None:
        self._cells = {path: StateCell(**cell) for path, cell in data.items()}


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable[[EventIR], None]]] = defaultdict(list)

    def subscribe(self, event_pattern: str, callback: Callable[[EventIR], None]) -> None:
        self._subscribers[event_pattern].append(callback)

    def publish(self, event: EventIR) -> None:
        for pattern, callbacks in self._subscribers.items():
            if fnmatch.fnmatch(event.event_type, pattern):
                for callback in callbacks:
                    callback(event)


class EventLog:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else None
        self.events: list[EventIR] = []
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: EventIR) -> None:
        self.events.append(event)
        if self.path:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")


class RuntimeModule(Protocol):
    contract: ModuleContract

    def evaluate(self, action: ActionIR, runtime: "WorldRuntime") -> TransitionResult: ...


class Scheduler:
    def __init__(self) -> None:
        self.tick = 0
        self._counter = 0
        self._queue: list[tuple[int, int, ActionIR]] = []

    def schedule(self, action: ActionIR, delay: int) -> None:
        self._counter += 1
        action.status = ActionStatus.SCHEDULED
        heapq.heappush(self._queue, (self.tick + max(0, delay), self._counter, action))

    def advance(self, ticks: int = 1) -> list[ActionIR]:
        self.tick += max(0, ticks)
        ready: list[ActionIR] = []
        while self._queue and self._queue[0][0] <= self.tick:
            ready.append(heapq.heappop(self._queue)[2])
        return ready

    @property
    def queued(self) -> int:
        return len(self._queue)


class WorldRuntime:
    def __init__(self, package: dict[str, Any], event_log_path: str | Path | None = None) -> None:
        self.package = package
        self.registry = EntityRegistry()
        self.state = StateStore()
        self.events = EventBus()
        self.event_log = EventLog(event_log_path)
        self.scheduler = Scheduler()
        self.modules: dict[str, RuntimeModule] = {}
        self.actions: dict[str, ActionIR] = {}
        self.metrics: Counter[str] = Counter()
        for raw in package["entities"]:
            self.registry.add(Entity(**raw))
        for raw in package["initial_state"]:
            self.state.seed(raw["owner"], raw["namespace"], raw["key"], raw["value"], raw.get("version", 0))

    @classmethod
    def from_package(cls, path: str | Path, event_log_path: str | Path | None = None) -> "WorldRuntime":
        package = json.loads(Path(path).read_text(encoding="utf-8"))
        if package.get("format") != "compilableworld.runtime-package/v0.1":
            raise RuntimeErrorBase("不支援的 Runtime Package")
        return cls(package, event_log_path)

    def register_module(self, module: RuntimeModule) -> None:
        contract = module.contract
        if contract.module_id in self.modules:
            raise RuntimeErrorBase(f"重複模組: {contract.module_id}")
        self.modules[contract.module_id] = module
        on_register = getattr(module, "on_register", None)
        if callable(on_register):
            on_register(self)

    def commit_reaction(
        self, module: RuntimeModule, deltas: list[StateDelta], events: list[EventIR],
    ) -> list[dict[str, Any]]:
        """Event-subscriber commit path: same Delta+Event contract as `_execute`,
        for modules reacting to another module's event instead of a submitted
        Action (paper 07 §4.6 — modules cooperate via events, never direct calls)."""
        applied = self.state.commit(deltas, module.contract.write)
        commit_event = EventIR(
            event_type="state.committed", source=module.contract.module_id,
            timestamp_tick=self.scheduler.tick, visibility="audit", payload={"applied": applied},
        )
        for event in (commit_event, *events):
            event.timestamp_tick = self.scheduler.tick
            self.event_log.append(event)
            self.events.publish(event)
            self.metrics[f"event:{event.event_type}"] += 1
        return applied

    def module_for(self, verb: str) -> RuntimeModule:
        candidates = [m for m in self.modules.values() if verb in m.contract.actions]
        if len(candidates) != 1:
            raise RuntimeErrorBase(f"行為 {verb} 的提供者數量不是 1: {len(candidates)}")
        return candidates[0]

    def submit(self, action: ActionIR, delay: int = 0) -> ActionReceipt:
        action.proposed_at_tick = self.scheduler.tick
        action.status = ActionStatus.PARSED
        self.actions[action.action_id] = action
        if not self.registry.contains(action.actor_id):
            return self._fail(action, f"未知 actor: {action.actor_id}")
        if delay > 0:
            self.scheduler.schedule(action, delay)
            return ActionReceipt(action.action_id, action.status, f"已排程於 {delay} tick 後執行")
        return self._execute(action)

    def _execute(self, action: ActionIR) -> ActionReceipt:
        try:
            module = self.module_for(action.verb)
            action.status = ActionStatus.VALIDATED
            action.status = ActionStatus.EXECUTING
            result = module.evaluate(action, self)
            if not result.accepted:
                return self._fail(action, result.message)
            applied = self.state.commit(result.deltas, module.contract.write)
            commit_event = EventIR(
                event_type="state.committed", source=module.contract.module_id,
                target=action.actor_id, causation_id=action.action_id,
                correlation_id=action.correlation_id, timestamp_tick=self.scheduler.tick,
                visibility="audit", payload={"applied": applied},
            )
            emitted = [commit_event, *result.events]
            for event in emitted:
                event.causation_id = event.causation_id or action.action_id
                event.correlation_id = event.correlation_id or action.correlation_id
                event.timestamp_tick = self.scheduler.tick
                self.event_log.append(event)
                self.events.publish(event)
                self.metrics[f"event:{event.event_type}"] += 1
            action.status = ActionStatus.COMPLETED
            self.metrics["actions_completed"] += 1
            return ActionReceipt(
                action.action_id, action.status, result.message,
                [event.event_id for event in emitted], [item["path"] for item in applied],
            )
        except RuntimeErrorBase as exc:
            return self._fail(action, str(exc))

    def _fail(self, action: ActionIR, message: str) -> ActionReceipt:
        action.status = ActionStatus.FAILED
        self.metrics["actions_failed"] += 1
        event = EventIR(
            event_type="action.failed", source="kernel", target=action.actor_id,
            causation_id=action.action_id, correlation_id=action.correlation_id,
            timestamp_tick=self.scheduler.tick, visibility="private",
            payload={"verb": action.verb, "reason": message},
        )
        self.event_log.append(event)
        self.events.publish(event)
        return ActionReceipt(action.action_id, action.status, message, [event.event_id])

    def advance(self, ticks: int = 1) -> list[ActionReceipt]:
        return [self._execute(action) for action in self.scheduler.advance(ticks)]

    def save_snapshot(self, path: str | Path) -> None:
        payload = {
            "format": "compilableworld.snapshot/v0.1",
            "snapshot_id": new_id("snapshot"),
            "world_id": self.package["manifest"]["world_id"],
            "world_version": self.package["manifest"]["world_version"],
            "runtime_version": self.package["manifest"]["runtime_version"],
            "tick": self.scheduler.tick,
            "state": self.state.export(),
            "event_count": len(self.event_log.events),
        }
        Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def load_snapshot(self, path: str | Path) -> None:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if payload.get("world_id") != self.package["manifest"]["world_id"]:
            raise RuntimeErrorBase("Snapshot 屬於不同世界")
        self.state.import_state(payload["state"])
        self.scheduler.tick = int(payload["tick"])

    def replay(self, events: Iterable[EventIR]) -> None:
        for event in events:
            if event.event_type != "state.committed":
                continue
            for item in event.payload.get("applied", []):
                self.state.seed(
                    item["owner"], item["namespace"], item["key"],
                    item["value"], item["version"],
                )

    def diagnostics(self) -> dict[str, Any]:
        return {
            "world_id": self.package["manifest"]["world_id"],
            "world_version": self.package["manifest"]["world_version"],
            "tick": self.scheduler.tick,
            "entities": len(list(self.registry.values())),
            "states": len(self.state.export()),
            "modules": {key: value.contract.version for key, value in sorted(self.modules.items())},
            "queued_actions": self.scheduler.queued,
            "events": len(self.event_log.events),
            "metrics": dict(self.metrics),
        }
