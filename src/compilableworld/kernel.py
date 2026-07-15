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
from .functions import FunctionRegistry
from .player_generation import GeneratedPlayer, actor_id_for_player, template_records


class RuntimeErrorBase(RuntimeError):
    pass


SNAPSHOT_FORMAT_V1 = "compilableworld.snapshot/v0.1"
SNAPSHOT_FORMAT = "compilableworld.snapshot/v0.2"
SNAPSHOT_VERSION = 2


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

    def remove(self, entity_id: str) -> Entity | None:
        return self._entities.pop(entity_id, None)

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

    def remove_owner(self, owner: str) -> None:
        prefix = f"{owner}::"
        self._cells = {path: cell for path, cell in self._cells.items() if not path.startswith(prefix)}

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

    def export(self) -> dict[str, Any]:
        return {
            "tick": self.tick,
            "counter": self._counter,
            "queue": [
                {"due_tick": due_tick, "order": order, "action": action.to_dict()}
                for due_tick, order, action in sorted(self._queue, key=lambda item: (item[0], item[1]))
            ],
        }

    def import_state(self, payload: dict[str, Any]) -> list[ActionIR]:
        if not isinstance(payload, dict) or not isinstance(payload.get("queue", []), list):
            raise RuntimeErrorBase("Snapshot 的 scheduler.queue 格式無效")
        try:
            tick = int(payload.get("tick", 0))
            counter = int(payload.get("counter", 0))
        except (TypeError, ValueError) as exc:
            raise RuntimeErrorBase("Snapshot 的 scheduler tick/counter 格式無效") from exc
        if tick < 0 or counter < 0:
            raise RuntimeErrorBase("Snapshot 的 scheduler tick/counter 不可為負數")

        queue: list[tuple[int, int, ActionIR]] = []
        actions: list[ActionIR] = []
        max_order = counter
        try:
            for item in payload["queue"]:
                due_tick = int(item["due_tick"])
                order = int(item["order"])
                action = ActionIR.from_dict(item["action"])
                if due_tick < 0 or order < 1:
                    raise ValueError("負數 due_tick 或無效 order")
                action.status = ActionStatus.SCHEDULED
                queue.append((due_tick, order, action))
                actions.append(action)
                max_order = max(max_order, order)
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeErrorBase("Snapshot 的排程 Action 格式無效") from exc

        self.tick = tick
        self._counter = max_order
        self._queue = queue
        heapq.heapify(self._queue)
        return actions


class WorldRuntime:
    def __init__(self, package: dict[str, Any], event_log_path: str | Path | None = None) -> None:
        self.package = package
        self.functions = FunctionRegistry.from_package(package)
        self.registry = EntityRegistry()
        self.state = StateStore()
        self.events = EventBus()
        self.event_log = EventLog(event_log_path)
        self.scheduler = Scheduler()
        self.modules: dict[str, RuntimeModule] = {}
        self.actions: dict[str, ActionIR] = {}
        self.metrics: Counter[str] = Counter()
        self.dynamic_entities: set[str] = set()
        self.player_profiles: dict[str, dict[str, Any]] = {}
        self.active_player_id: str | None = None
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

    def player_templates(self) -> list[dict[str, Any]]:
        """Return the AI-proposed starter templates exposed to clients."""
        return template_records(self.package)

    def create_player(
        self,
        profile: GeneratedPlayer,
        *,
        actor_id: str | None = None,
        replace_actor_id: str | None = None,
        replace_default: bool = True,
    ) -> str:
        """Materialize a generated profile into the Runtime state model.

        Replacing an actor transfers carried items to the newly generated actor
        instead of leaving them with an entity that no longer exists.
        """
        existing_ids = set(self.registry._entities)
        if replace_actor_id:
            existing_ids.discard(replace_actor_id)
        if replace_default:
            default_id = self.package.get("world", {}).get("default_player_entity")
            if default_id:
                existing_ids.discard(default_id)
        candidate = actor_id or actor_id_for_player(profile, existing_ids)
        replacement_ids = set()
        if replace_actor_id:
            replacement_ids.add(replace_actor_id)
        if replace_default:
            default_id = self.package.get("world", {}).get("default_player_entity")
            if default_id:
                replacement_ids.add(default_id)
        carried_items = [
            (entity.entity_id, self.state.version(entity.entity_id, "inventory", "carrier"))
            for entity in self.registry.values()
            if entity.entity_id not in replacement_ids
            and self.state.get(entity.entity_id, "inventory", "carrier") in replacement_ids
        ]
        if self.registry.contains(candidate) and candidate not in replacement_ids:
            raise RuntimeErrorBase(f"player actor id already exists: {candidate}")
        for old_id in replacement_ids:
            if old_id == candidate or not self.registry.contains(old_id):
                continue
            self.registry.remove(old_id)
            self.state.remove_owner(old_id)
            self.dynamic_entities.discard(old_id)
            self.player_profiles.pop(old_id, None)
        if self.registry.contains(candidate):
            self.registry.remove(candidate)
            self.state.remove_owner(candidate)
            self.dynamic_entities.discard(candidate)
            self.player_profiles.pop(candidate, None)

        spawn = self.package.get("world", {}).get("player_spawn")
        if not spawn:
            raise RuntimeErrorBase("world.player_spawn is required for generated players")
        self.registry.add(Entity(
            entity_id=candidate,
            entity_type="character",
            name=profile.name,
            components=["position", "health", "inventory", "quest", "combatant", "magic"],
            metadata={"provenance": "player_generated", "generation": profile.to_dict()},
        ))
        self.dynamic_entities.add(candidate)
        self.player_profiles[candidate] = profile.to_dict()
        self.active_player_id = candidate
        self.state.seed(candidate, "position", "room", spawn)
        for attr, value in profile.attributes.items():
            self.state.seed(candidate, "combat", attr, value)
        self.state.seed(candidate, "combat", "phase_tier", profile.phase_tier)
        self.state.seed(candidate, "health", "current", profile.hp_max)
        self.state.seed(candidate, "health", "max", profile.hp_max)
        self.state.seed(candidate, "status", "alive", True)
        self.state.seed(candidate, "magic", "mp_current", profile.mp_max)
        self.state.seed(candidate, "magic", "mp_max", profile.mp_max)
        self.state.seed(candidate, "magic", "fp_current", profile.fp_max)
        self.state.seed(candidate, "magic", "fp_max", profile.fp_max)
        self.state.seed(candidate, "wallet", "currency", 0)
        for quest in self.package.get("quests", []):
            self.state.seed(candidate, "quest", quest["quest_id"], quest["initial_state"])
        for item_id, version in carried_items:
            self.state.seed(item_id, "inventory", "carrier", candidate, version)
        return candidate

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
            "format": SNAPSHOT_FORMAT,
            "snapshot_version": SNAPSHOT_VERSION,
            "snapshot_id": new_id("snapshot"),
            "world_id": self.package["manifest"]["world_id"],
            "world_version": self.package["manifest"]["world_version"],
            "runtime_version": self.package["manifest"]["runtime_version"],
            "tick": self.scheduler.tick,
            "state": self.state.export(),
            "dynamic_entities": [
                asdict(self.registry.get(entity_id)) for entity_id in sorted(self.dynamic_entities)
            ],
            "player_profiles": self.player_profiles,
            "active_player_id": self.active_player_id,
            "scheduler": self.scheduler.export(),
            "event_count": len(self.event_log.events),
        }
        Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def load_snapshot(self, path: str | Path) -> None:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeErrorBase("Snapshot 根資料格式無效")
        snapshot_format = payload.get("format")
        if snapshot_format not in {SNAPSHOT_FORMAT_V1, SNAPSHOT_FORMAT}:
            raise RuntimeErrorBase("不支援的 Snapshot 格式")
        try:
            snapshot_version = int(payload.get("snapshot_version", 1 if snapshot_format == SNAPSHOT_FORMAT_V1 else 0))
        except (TypeError, ValueError) as exc:
            raise RuntimeErrorBase("Snapshot 版本格式無效") from exc
        if snapshot_version < 1 or snapshot_version > SNAPSHOT_VERSION:
            raise RuntimeErrorBase(f"不支援的 Snapshot 版本: {snapshot_version}")
        if payload.get("world_id") != self.package["manifest"]["world_id"]:
            raise RuntimeErrorBase("Snapshot 屬於不同世界")
        if payload.get("world_version") != self.package["manifest"]["world_version"]:
            raise RuntimeErrorBase("Snapshot 屬於不相容的世界版本")
        if not isinstance(payload.get("state"), dict):
            raise RuntimeErrorBase("Snapshot 缺少有效 state")
        # Parse and validate every replacement structure before touching live
        # Runtime objects. A malformed scheduler or entity must not leave a
        # hybrid world behind after load_snapshot raises.
        dynamic_payload = payload.get("dynamic_entities", [])
        if not isinstance(dynamic_payload, list):
            raise RuntimeErrorBase("Snapshot dynamic_entities must be a list")
        static_entity_ids = {raw["entity_id"] for raw in self.package["entities"]}
        snapshot_entities: dict[str, Entity] = {}
        try:
            for raw in dynamic_payload:
                if not isinstance(raw, dict):
                    raise TypeError("dynamic entity must be an object")
                entity = Entity(**raw)
                if not entity.entity_id or entity.entity_id in static_entity_ids:
                    raise ValueError(f"invalid dynamic entity id: {entity.entity_id}")
                if entity.entity_id in snapshot_entities:
                    raise ValueError(f"duplicate dynamic entity id: {entity.entity_id}")
                if not isinstance(entity.components, list) or not isinstance(entity.metadata, dict):
                    raise TypeError(f"invalid dynamic entity shape: {entity.entity_id}")
                snapshot_entities[entity.entity_id] = entity
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeErrorBase("Snapshot dynamic_entities is invalid") from exc

        profiles_payload = payload.get("player_profiles", {})
        if not isinstance(profiles_payload, dict) or any(
            not isinstance(player_id, str) or not isinstance(profile, dict)
            for player_id, profile in profiles_payload.items()
        ):
            raise RuntimeErrorBase("Snapshot player_profiles is invalid")
        if set(profiles_payload) - set(snapshot_entities):
            raise RuntimeErrorBase("Snapshot player_profiles references missing entities")
        next_profiles = {player_id: dict(profile) for player_id, profile in profiles_payload.items()}

        active_player_id = payload.get("active_player_id")
        if active_player_id is not None and (
            not isinstance(active_player_id, str) or active_player_id not in snapshot_entities
        ):
            raise RuntimeErrorBase("Snapshot active_player_id references a missing entity")

        next_state = StateStore()
        try:
            next_state.import_state(payload["state"])
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise RuntimeErrorBase("Snapshot state is invalid") from exc

        scheduler_payload = payload.get("scheduler")
        if snapshot_version == 1 or scheduler_payload is None:
            # v0.1 snapshots predate scheduler persistence; migrate them as an
            # empty queue while retaining their saved tick.
            scheduler_payload = {"tick": payload.get("tick", 0), "counter": 0, "queue": []}
        next_scheduler = Scheduler()
        queued_actions = next_scheduler.import_state(scheduler_payload)
        next_actions = {action.action_id: action for action in queued_actions}

        preserved_entities = {
            entity_id: entity
            for entity_id, entity in self.registry._entities.items()
            if entity_id not in self.dynamic_entities
        }
        conflicts = set(snapshot_entities).intersection(preserved_entities)
        if conflicts:
            raise RuntimeErrorBase(
                "Snapshot dynamic_entities conflict with existing entities: "
                + ", ".join(sorted(conflicts))
            )
        next_entities = {**preserved_entities, **snapshot_entities}

        # Commit the validated replacement as one state transition while
        # retaining object identity for StateStore/Scheduler references held by
        # modules and adapters.
        self.registry._entities = next_entities
        self.dynamic_entities = set(snapshot_entities)
        self.player_profiles = next_profiles
        self.active_player_id = active_player_id
        self.state._cells = next_state._cells
        self.scheduler.tick = next_scheduler.tick
        self.scheduler._counter = next_scheduler._counter
        self.scheduler._queue = next_scheduler._queue
        self.actions = next_actions

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
            "functions": self.functions.describe(),
            "function_cache": self.functions.cache_stats(),
            "queued_actions": self.scheduler.queued,
            "events": len(self.event_log.events),
            "active_player_id": self.active_player_id,
            "generated_players": sorted(self.player_profiles),
            "metrics": dict(self.metrics),
        }
