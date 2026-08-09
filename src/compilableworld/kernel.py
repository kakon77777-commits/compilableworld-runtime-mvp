from __future__ import annotations

import fnmatch
import heapq
import json
import math
import os
from copy import deepcopy
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Iterable, Protocol

from .action_behavior import (
    ACTION_BEHAVIOR_CONDITION_NAMESPACES,
    ACTION_BEHAVIOR_CONDITION_OPERATORS,
    ACTION_BEHAVIOR_CONDITION_SUBJECTS,
    ACTION_BEHAVIOR_DURATION_LIMIT,
    ACTION_BEHAVIOR_INTERRUPT_EVENTS,
    ACTION_BEHAVIOR_RETRY_ATTEMPT_LIMIT,
)
from .models import (
    ActionIR, ActionReceipt, ActionStatus, Entity, EventIR, ModuleContract,
    StateCell, StateDelta, TransitionResult, new_id,
)
from .functions import FunctionRegistry
from .player_generation import GeneratedPlayer, actor_id_for_player, template_records


class RuntimeErrorBase(RuntimeError):
    pass


class KernelTransactionError(RuntimeErrorBase):
    """Durable Kernel state/event commit failed and was rolled back locally."""

    pass


SNAPSHOT_FORMAT_V1 = "compilableworld.snapshot/v0.1"
SNAPSHOT_FORMAT_V2 = "compilableworld.snapshot/v0.2"
SNAPSHOT_FORMAT = "compilableworld.snapshot/v0.3"
SNAPSHOT_VERSION = 3


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
            self._load_existing()

    def _load_existing(self) -> None:
        if self.path is None or not self.path.exists():
            return
        seen_ids: set[str] = set()
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise RuntimeErrorBase(f"EventLog cannot be read: {self.path}") from exc
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                if not isinstance(payload, dict):
                    raise ValueError("event record must be an object")
                event = EventIR(**payload)
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise RuntimeErrorBase(
                    f"EventLog record is invalid at line {line_number}: {self.path}"
                ) from exc
            if not isinstance(event.payload, dict) or not event.event_id:
                raise RuntimeErrorBase(f"EventLog record is invalid at line {line_number}: {self.path}")
            if event.event_id in seen_ids:
                raise RuntimeErrorBase(f"EventLog contains duplicate event_id at line {line_number}: {self.path}")
            seen_ids.add(event.event_id)
            self.events.append(event)

    def append(self, event: EventIR) -> None:
        self.append_batch([event])

    def append_batch(self, events: Iterable[EventIR]) -> None:
        batch = list(events)
        if not batch:
            return
        encoded = "".join(json.dumps(event.to_dict(), ensure_ascii=False) + "\n" for event in batch)
        if self.path is None:
            self.events.extend(batch)
            return

        start_offset = self.path.stat().st_size if self.path.exists() else 0
        try:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as exc:
            try:
                with self.path.open("r+b") as handle:
                    handle.truncate(start_offset)
            except OSError:
                pass
            raise KernelTransactionError("EventLog batch append failed") from exc
        self.events.extend(batch)


class RuntimeModule(Protocol):
    contract: ModuleContract

    def evaluate(self, action: ActionIR, runtime: "WorldRuntime") -> TransitionResult: ...


class Scheduler:
    def __init__(self) -> None:
        self.tick = 0
        self._counter = 0
        self._queue: list[tuple[int, int, ActionIR]] = []

    def schedule(self, action: ActionIR, delay: int) -> tuple[int, int, ActionIR]:
        self._counter += 1
        action.status = ActionStatus.SCHEDULED
        entry = (self.tick + max(0, delay), self._counter, action)
        heapq.heappush(self._queue, entry)
        return entry

    def remove(self, action_id: str) -> tuple[int, int, ActionIR] | None:
        for index, entry in enumerate(self._queue):
            if entry[2].action_id != action_id:
                continue
            removed = self._queue.pop(index)
            heapq.heapify(self._queue)
            return removed
        return None

    def restore(self, entry: tuple[int, int, ActionIR]) -> None:
        self._counter = max(self._counter, entry[1])
        heapq.heappush(self._queue, entry)

    def entries(self) -> list[tuple[int, int, ActionIR]]:
        return sorted(self._queue, key=lambda item: (item[0], item[1]))

    def advance(self, ticks: int = 1) -> list[ActionIR]:
        self.tick += max(0, ticks)
        return self.pop_ready()

    def pop_ready(self) -> list[ActionIR]:
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
        self.action_runtime: dict[str, dict[str, Any]] = {}
        self.metrics: Counter[str] = Counter()
        self.dynamic_entities: set[str] = set()
        self.player_profiles: dict[str, dict[str, Any]] = {}
        self.active_player_id: str | None = None
        self._action_interrupts_bound = False
        for raw in package["entities"]:
            self.registry.add(Entity(**raw))
        for raw in package["initial_state"]:
            self.state.seed(raw["owner"], raw["namespace"], raw["key"], raw["value"], raw.get("version", 0))

    def bind_action_interrupts(self) -> None:
        """Register Kernel lifecycle reactions after optional raw observers."""
        if self._action_interrupts_bound:
            return
        interrupt_events = {
            event_type
            for behavior in self.package.get("action_behaviors", [])
            for event_type in behavior.get("interrupt_on", [])
            if event_type in ACTION_BEHAVIOR_INTERRUPT_EVENTS
        }
        for event_type in sorted(interrupt_events):
            self.events.subscribe(event_type, self._on_action_interrupt_event)
        self._action_interrupts_bound = True

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
        state_before = deepcopy(self.state.export())
        try:
            applied = self.state.commit(deltas, module.contract.write)
        except RuntimeErrorBase:
            self.state.import_state(state_before)
            raise
        commit_event = EventIR(
            event_type="state.committed", source=module.contract.module_id,
            timestamp_tick=self.scheduler.tick, visibility="audit", payload={"applied": applied},
        )
        emitted = [commit_event, *events]
        for event in emitted:
            event.timestamp_tick = self.scheduler.tick
        try:
            self.event_log.append_batch(emitted)
        except KernelTransactionError:
            self.state.import_state(state_before)
            raise
        for event in emitted:
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
        try:
            module = self.module_for(action.verb)
        except RuntimeErrorBase as exc:
            return self._fail(action, str(exc))
        behavior = self._action_behavior(action.verb)
        if behavior and module.contract.module_id != behavior["completion_module"]:
            return self._fail(
                action,
                f"行為 {action.verb} 的 completion_module 契約不符: "
                f"{module.contract.module_id} != {behavior['completion_module']}",
            )
        if behavior:
            duration = behavior["duration_ticks"]
            if delay not in {0, duration}:
                return self._fail(action, f"行為 {action.verb} 的 duration 固定為 {duration} tick")
            if any(
                queued.actor_id == action.actor_id and self._action_behavior(queued.verb) is not None
                for _, _, queued in self.scheduler.entries()
            ):
                return self._fail(action, "同一 actor 同時間只能執行一個 authored long action")
            delay = duration
        if delay > 0:
            entry = self.scheduler.schedule(action, delay)
            self.action_runtime[action.action_id] = {"retries": {}}
            event = self._action_lifecycle_event("action.scheduled", action, behavior, due_tick=entry[0])
            try:
                self.event_log.append(event)
            except KernelTransactionError:
                self.scheduler.remove(action.action_id)
                self.actions.pop(action.action_id, None)
                self.action_runtime.pop(action.action_id, None)
                action.status = ActionStatus.PARSED
                raise
            self.events.publish(event)
            self.metrics["actions_scheduled"] += 1
            self.metrics[f"event:{event.event_type}"] += 1
            title = behavior["title"] if behavior else action.verb
            return ActionReceipt(
                action.action_id, action.status,
                f"{title} 已排程，將於 {delay} tick 後完成（action_id={action.action_id}）",
                [event.event_id],
            )
        return self._execute(action)

    def _execute(self, action: ActionIR) -> ActionReceipt:
        scheduled_behavior = self._action_behavior(action.verb) if action.status == ActionStatus.SCHEDULED else None
        started_event = (
            self._action_lifecycle_event("action.started", action, scheduled_behavior)
            if scheduled_behavior else None
        )
        state_before = deepcopy(self.state.export())
        try:
            module = self.module_for(action.verb)
            action.status = ActionStatus.VALIDATED
            action.status = ActionStatus.EXECUTING
            result = module.evaluate(action, self)
            if not result.accepted:
                return self._fail(action, result.message, lifecycle_started=scheduled_behavior is not None)
            applied = self.state.commit(result.deltas, module.contract.write)
            commit_event = EventIR(
                event_type="state.committed", source=module.contract.module_id,
                target=action.actor_id, causation_id=action.action_id,
                correlation_id=action.correlation_id, timestamp_tick=self.scheduler.tick,
                visibility="audit", payload={"applied": applied},
            )
            completed_event = (
                self._action_lifecycle_event("action.completed", action, scheduled_behavior)
                if scheduled_behavior else None
            )
            emitted = [
                *([started_event] if started_event else []),
                commit_event,
                *result.events,
                *([completed_event] if completed_event else []),
            ]
            for event in emitted:
                event.causation_id = event.causation_id or action.action_id
                event.correlation_id = event.correlation_id or action.correlation_id
                event.timestamp_tick = self.scheduler.tick
            self.event_log.append_batch(emitted)
        except KernelTransactionError:
            self.state.import_state(state_before)
            action.status = ActionStatus.FAILED
            self.action_runtime.pop(action.action_id, None)
            self.metrics["actions_failed"] += 1
            raise
        except RuntimeErrorBase as exc:
            self.state.import_state(state_before)
            return self._fail(action, str(exc), lifecycle_started=scheduled_behavior is not None)
        action.status = ActionStatus.COMPLETED
        self.action_runtime.pop(action.action_id, None)
        self.metrics["actions_completed"] += 1
        for event in emitted:
            self.events.publish(event)
            self.metrics[f"event:{event.event_type}"] += 1
        return ActionReceipt(
            action.action_id, action.status, result.message,
            [event.event_id for event in emitted], [item["path"] for item in applied],
        )

    def _fail(
        self, action: ActionIR, message: str, *, lifecycle_started: bool = False,
    ) -> ActionReceipt:
        action.status = ActionStatus.FAILED
        self.metrics["actions_failed"] += 1
        behavior = self._action_behavior(action.verb)
        started = (
            self._action_lifecycle_event("action.started", action, behavior)
            if lifecycle_started and behavior else None
        )
        payload = {"verb": action.verb, "reason": message}
        if behavior:
            payload.update({
                "action_id": action.action_id,
                "behavior_id": behavior["behavior_id"],
                "actor": action.actor_id,
            })
        event = EventIR(
            event_type="action.failed", source="kernel", target=action.actor_id,
            causation_id=action.action_id, correlation_id=action.correlation_id,
            timestamp_tick=self.scheduler.tick, visibility="private",
            payload=payload,
        )
        emitted = [*([started] if started else []), event]
        try:
            self.event_log.append_batch(emitted)
        except KernelTransactionError:
            self.action_runtime.pop(action.action_id, None)
            raise
        self.action_runtime.pop(action.action_id, None)
        for emitted_event in emitted:
            self.events.publish(emitted_event)
            self.metrics[f"event:{emitted_event.event_type}"] += 1
        return ActionReceipt(
            action.action_id, action.status, message,
            [emitted_event.event_id for emitted_event in emitted],
        )

    def _action_behavior(self, verb: str) -> dict[str, Any] | None:
        return next(
            (
                behavior for behavior in self.package.get("action_behaviors", [])
                if behavior.get("verb") == verb
            ),
            None,
        )

    def _action_lifecycle_event(
        self,
        event_type: str,
        action: ActionIR,
        behavior: dict[str, Any] | None,
        *,
        due_tick: int | None = None,
        reason: str | None = None,
        causation_id: str | None = None,
    ) -> EventIR:
        duration = behavior["duration_ticks"] if behavior else max(
            0, (due_tick or self.scheduler.tick) - action.proposed_at_tick,
        )
        payload: dict[str, Any] = {
            "action_id": action.action_id,
            "behavior_id": behavior["behavior_id"] if behavior else None,
            "actor": action.actor_id,
            "verb": action.verb,
            "duration_ticks": duration,
        }
        if due_tick is not None:
            payload["due_tick"] = due_tick
        if event_type == "action.scheduled":
            payload["action"] = action.to_dict()
        if reason is not None:
            payload["reason"] = reason
        return EventIR(
            event_type=event_type,
            source="kernel",
            target=action.actor_id,
            causation_id=causation_id or action.action_id,
            correlation_id=action.correlation_id,
            timestamp_tick=self.scheduler.tick,
            visibility="private",
            payload=payload,
        )

    def pending_actions(self, actor_id: str | None = None) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for due_tick, _, action in self.scheduler.entries():
            if actor_id is not None and action.actor_id != actor_id:
                continue
            behavior = self._action_behavior(action.verb)
            duration = behavior["duration_ticks"] if behavior else max(
                0, due_tick - action.proposed_at_tick,
            )
            started_tick = due_tick - duration
            progress = min(duration, max(0, self.scheduler.tick - started_tick))
            authored_phases = list(behavior.get("phases", [])) if behavior else []
            phases = [
                {
                    "phase_id": phase["phase_id"],
                    "title": phase["title"],
                    "duration_ticks": phase["duration_ticks"],
                    "condition_ids": [
                        condition["condition_id"]
                        for condition in phase.get("when", [])
                        if isinstance(condition, dict) and isinstance(condition.get("condition_id"), str)
                    ],
                    "retry_policy": dict(phase["retry"])
                    if isinstance(phase.get("retry"), dict) else None,
                }
                for phase in authored_phases if isinstance(phase, dict)
            ]
            completed_phases = 0
            elapsed_boundary = 0
            for phase in phases:
                elapsed_boundary += phase["duration_ticks"]
                if elapsed_boundary <= progress:
                    completed_phases += 1
            current_phase = (
                dict(phases[min(completed_phases, len(phases) - 1)]) if phases else None
            )
            retry_records = self.action_runtime.get(action.action_id, {}).get("retries", {})
            if retry_records:
                retry_phase_id = next(iter(retry_records))
                retry_phase_index = next(
                    (
                        index for index, phase in enumerate(phases)
                        if phase["phase_id"] == retry_phase_id
                    ),
                    0,
                )
                progress = sum(
                    phase["duration_ticks"] for phase in phases[:retry_phase_index]
                )
                completed_phases = retry_phase_index
                current_phase = dict(phases[max(0, retry_phase_index - 1)])
            active_retries = [
                {
                    "phase_id": phase_id,
                    "condition_id": retry_state.get("condition_id"),
                    "attempts": retry_state.get("attempts"),
                    "max_attempts": next(
                        (
                            phase["retry_policy"]["max_attempts"]
                            for phase in phases
                            if phase["phase_id"] == phase_id
                            and isinstance(phase.get("retry_policy"), dict)
                        ),
                        None,
                    ),
                    "next_retry_tick": retry_state.get("next_retry_tick"),
                    "timeout_at_tick": retry_state.get("timeout_at_tick"),
                }
                for phase_id, retry_state in sorted(retry_records.items())
                if isinstance(retry_state, dict)
            ]
            records.append({
                "action_id": action.action_id,
                "actor_id": action.actor_id,
                "verb": action.verb,
                "behavior_id": behavior["behavior_id"] if behavior else None,
                "title": behavior["title"] if behavior else action.verb,
                "status": action.status.value,
                "started_tick": started_tick,
                "due_tick": due_tick,
                "duration_ticks": duration,
                "progress_ticks": progress,
                "remaining_ticks": max(0, due_tick - self.scheduler.tick),
                "interrupt_on": list(behavior["interrupt_on"]) if behavior else [],
                "phases": [dict(phase) for phase in phases],
                "completed_phase_count": completed_phases,
                "current_phase": current_phase,
                "active_retries": active_retries,
            })
        return records

    def cancel_action(self, actor_id: str, action_id: str) -> ActionReceipt:
        if not self.registry.contains(actor_id):
            raise RuntimeErrorBase(f"未知 actor: {actor_id}")
        entry = next(
            (entry for entry in self.scheduler.entries() if entry[2].action_id == action_id),
            None,
        )
        if entry is None:
            raise RuntimeErrorBase(f"找不到待執行 action: {action_id}")
        if entry[2].actor_id != actor_id:
            raise RuntimeErrorBase("不可取消其他 actor 的 action")
        return self._terminate_scheduled_action(entry, ActionStatus.CANCELLED, "由 actor 取消")

    def _on_action_interrupt_event(self, event: EventIR) -> None:
        actor_id = event.target
        if not isinstance(actor_id, str):
            return
        for entry in self.scheduler.entries():
            action = entry[2]
            behavior = self._action_behavior(action.verb)
            if (
                action.actor_id == actor_id
                and behavior is not None
                and event.event_type in behavior["interrupt_on"]
            ):
                self._terminate_scheduled_action(
                    entry,
                    ActionStatus.INTERRUPTED,
                    f"被 {event.event_type} 中斷",
                    cause_event=event,
                )

    def _terminate_scheduled_action(
        self,
        entry: tuple[int, int, ActionIR],
        status: ActionStatus,
        reason: str,
        *,
        cause_event: EventIR | None = None,
    ) -> ActionReceipt:
        due_tick, _, action = entry
        removed = self.scheduler.remove(action.action_id)
        if removed is None:
            raise RuntimeErrorBase(f"待執行 action 已不存在: {action.action_id}")
        previous_status = action.status
        action.status = status
        event_type = "action.cancelled" if status == ActionStatus.CANCELLED else "action.interrupted"
        event = self._action_lifecycle_event(
            event_type,
            action,
            self._action_behavior(action.verb),
            due_tick=due_tick,
            reason=reason,
            causation_id=cause_event.event_id if cause_event else action.action_id,
        )
        try:
            self.event_log.append(event)
        except KernelTransactionError:
            action.status = previous_status
            self.scheduler.restore(removed)
            raise
        self.action_runtime.pop(action.action_id, None)
        self.events.publish(event)
        self.metrics[f"actions_{status.value}"] += 1
        self.metrics[f"event:{event.event_type}"] += 1
        return ActionReceipt(action.action_id, action.status, reason, [event.event_id])

    def advance(self, ticks: int = 1) -> list[ActionReceipt]:
        receipts: list[ActionReceipt] = []
        for _ in range(max(0, ticks)):
            next_tick = self.scheduler.tick + 1
            decisions = self._action_checkpoint_decisions(next_tick)
            queue_before = list(self.scheduler._queue)
            counter_before = self.scheduler._counter
            statuses_before = {
                action.action_id: action.status for _, _, action in queue_before
            }
            action_runtime_before = deepcopy(self.action_runtime)
            self.scheduler.tick = next_tick
            for event, entry, outcome, _ in decisions:
                action = entry[2]
                if outcome == "progress":
                    retry_state = self.action_runtime.get(action.action_id, {}).get("retries", {})
                    retry_state.pop(event.payload["next_phase_id"], None)
                    continue
                removed = self.scheduler.remove(action.action_id)
                if removed is None:
                    raise RuntimeErrorBase(f"checkpoint action 已不在排程中: {action.action_id}")
                if outcome == "retry":
                    self.scheduler.restore((event.payload["due_tick"], removed[1], action))
                    retries = self.action_runtime.setdefault(
                        action.action_id, {"retries": {}}
                    )["retries"]
                    retries[event.payload["phase_id"]] = {
                        "attempts": event.payload["attempt"],
                        "first_failure_tick": event.payload["first_failure_tick"],
                        "timeout_at_tick": event.payload["timeout_at_tick"],
                        "next_retry_tick": event.payload["retry_at_tick"],
                        "condition_id": event.payload["condition_id"],
                    }
                else:
                    action.status = ActionStatus.FAILED
                    self.action_runtime.pop(action.action_id, None)
            try:
                self.event_log.append_batch(event for event, _, _, _ in decisions)
            except KernelTransactionError:
                self.scheduler.tick -= 1
                self.scheduler._counter = counter_before
                self.scheduler._queue = queue_before
                heapq.heapify(self.scheduler._queue)
                for _, _, action in queue_before:
                    action.status = statuses_before[action.action_id]
                self.action_runtime = action_runtime_before
                raise
            for event, entry, outcome, message in decisions:
                action = entry[2]
                if outcome == "failed":
                    self.metrics["actions_failed"] += 1
                    receipts.append(ActionReceipt(
                        action.action_id, action.status, message or "phase condition failed",
                        [event.event_id],
                    ))
                elif outcome == "retry":
                    self.metrics["actions_retried"] += 1
                    receipts.append(ActionReceipt(
                        action.action_id, action.status, message or "phase retry scheduled",
                        [event.event_id],
                    ))
                self.events.publish(event)
                self.metrics[f"event:{event.event_type}"] += 1
            receipts.extend(self._execute(action) for action in self.scheduler.pop_ready())
        return receipts

    def _action_checkpoint_decisions(
        self, tick: int,
    ) -> list[tuple[EventIR, tuple[int, int, ActionIR], str, str | None]]:
        decisions: list[tuple[EventIR, tuple[int, int, ActionIR], str, str | None]] = []
        for entry in self.scheduler.entries():
            due_tick, _, action = entry
            behavior = self._action_behavior(action.verb)
            phases = behavior.get("phases", []) if isinstance(behavior, dict) else []
            if not isinstance(phases, list) or len(phases) < 2:
                continue
            active_retries = self.action_runtime.get(action.action_id, {}).get("retries", {})
            if active_retries and tick not in {
                retry_state.get("next_retry_tick")
                for retry_state in active_retries.values()
                if isinstance(retry_state, dict)
            }:
                continue
            duration = behavior["duration_ticks"]
            start_tick = due_tick - duration
            elapsed = tick - start_tick
            cumulative = 0
            for phase_index, phase in enumerate(phases[:-1]):
                cumulative += phase["duration_ticks"]
                if elapsed != cumulative:
                    continue
                next_phase = phases[phase_index + 1]
                failed_condition = next(
                    (
                        condition for condition in next_phase.get("when", [])
                        if not self._action_condition_matches(action, condition)
                    ),
                    None,
                )
                if failed_condition is not None:
                    condition_id = failed_condition.get("condition_id")
                    if not isinstance(condition_id, str) or not condition_id:
                        condition_id = "invalid_condition"
                    message = (
                        f"行為 {behavior['title']} 無法進入 phase {next_phase['title']}："
                        f"條件 {condition_id} 未滿足"
                    )
                    raw_retry_policy = next_phase.get("retry")
                    retry_policy = self._bounded_action_retry_policy(raw_retry_policy)
                    retry_state = self.action_runtime.get(action.action_id, {}).get(
                        "retries", {}
                    ).get(next_phase["phase_id"])
                    if isinstance(retry_policy, dict):
                        first_failure_tick = (
                            retry_state["first_failure_tick"]
                            if isinstance(retry_state, dict) else tick
                        )
                        attempt = (
                            retry_state["attempts"] + 1
                            if isinstance(retry_state, dict) else 1
                        )
                        retry_at_tick = tick + retry_policy["interval_ticks"]
                        timeout_at_tick = first_failure_tick + retry_policy["timeout_ticks"]
                        if (
                            attempt <= retry_policy["max_attempts"]
                            and retry_at_tick <= timeout_at_tick
                        ):
                            retry_message = (
                                f"{message}；retry {attempt}/{retry_policy['max_attempts']} "
                                f"scheduled for tick {retry_at_tick}"
                            )
                            decisions.append((EventIR(
                                event_type="action.retry_scheduled",
                                source="kernel",
                                target=action.actor_id,
                                causation_id=action.action_id,
                                correlation_id=action.correlation_id,
                                timestamp_tick=tick,
                                visibility="private",
                                payload={
                                    "action_id": action.action_id,
                                    "behavior_id": behavior["behavior_id"],
                                    "actor": action.actor_id,
                                    "verb": action.verb,
                                    "duration_ticks": duration,
                                    "phase_id": next_phase["phase_id"],
                                    "condition_id": condition_id,
                                    "attempt": attempt,
                                    "max_attempts": retry_policy["max_attempts"],
                                    "interval_ticks": retry_policy["interval_ticks"],
                                    "first_failure_tick": first_failure_tick,
                                    "retry_at_tick": retry_at_tick,
                                    "timeout_at_tick": timeout_at_tick,
                                    "due_tick": due_tick + retry_policy["interval_ticks"],
                                    "reason": retry_message,
                                },
                            ), entry, "retry", retry_message))
                            continue
                    failure_code = (
                        "retry_exhausted" if isinstance(retry_policy, dict)
                        else "invalid_retry_policy" if raw_retry_policy is not None
                        else "condition_failed"
                    )
                    failure_payload = {
                        "action_id": action.action_id,
                        "behavior_id": behavior["behavior_id"],
                        "actor": action.actor_id,
                        "verb": action.verb,
                        "duration_ticks": duration,
                        "phase_id": next_phase["phase_id"],
                        "condition_id": condition_id,
                        "failure_code": failure_code,
                        "reason": message,
                    }
                    if isinstance(retry_policy, dict):
                        failure_payload.update({
                            "attempt": attempt,
                            "max_attempts": retry_policy["max_attempts"],
                            "timeout_at_tick": timeout_at_tick,
                        })
                    decisions.append((EventIR(
                        event_type="action.failed",
                        source="kernel",
                        target=action.actor_id,
                        causation_id=action.action_id,
                        correlation_id=action.correlation_id,
                        timestamp_tick=tick,
                        visibility="private",
                        payload=failure_payload,
                    ), entry, "failed", message))
                    continue
                decisions.append((EventIR(
                    event_type="action.progressed",
                    source="kernel",
                    target=action.actor_id,
                    causation_id=action.action_id,
                    correlation_id=action.correlation_id,
                    timestamp_tick=tick,
                    visibility="private",
                    payload={
                        "action_id": action.action_id,
                        "behavior_id": behavior["behavior_id"],
                        "actor": action.actor_id,
                        "verb": action.verb,
                        "phase_id": phase["phase_id"],
                        "phase_title": phase["title"],
                        "phase_index": phase_index + 1,
                        "completed_phases": phase_index + 1,
                        "total_phases": len(phases),
                        "next_phase_id": next_phase["phase_id"],
                        "progress_ticks": cumulative,
                        "duration_ticks": duration,
                    },
                ), entry, "progress", None))
        return decisions

    def _action_condition_matches(self, action: ActionIR, condition: Any) -> bool:
        if not isinstance(condition, dict):
            return False
        condition_id = condition.get("condition_id")
        subject = condition.get("subject")
        namespace = condition.get("namespace")
        key = condition.get("key")
        operator = condition.get("operator")
        if (
            not isinstance(condition_id, str)
            or not condition_id
            or subject not in ACTION_BEHAVIOR_CONDITION_SUBJECTS
            or namespace not in ACTION_BEHAVIOR_CONDITION_NAMESPACES
            or not isinstance(key, str)
            or operator not in ACTION_BEHAVIOR_CONDITION_OPERATORS
        ):
            return False
        owner = action.actor_id if subject == "actor" else action.target_id
        if not isinstance(owner, str) or not self.registry.contains(owner):
            return False
        missing = object()
        actual = self.state.get(owner, namespace, key, missing)
        if actual is missing or not self._finite_condition_scalar(actual):
            return False
        expected = condition.get("value")
        if not self._finite_condition_scalar(expected):
            return False
        if operator in {"equals", "not_equals"}:
            equal = self._strict_scalar_equal(actual, expected)
            return equal if operator == "equals" else not equal
        if (
            isinstance(actual, bool)
            or isinstance(expected, bool)
            or not isinstance(actual, (int, float))
            or not isinstance(expected, (int, float))
        ):
            return False
        return {
            "less_than": actual < expected,
            "less_or_equal": actual <= expected,
            "greater_than": actual > expected,
            "greater_or_equal": actual >= expected,
        }[operator]

    @staticmethod
    def _strict_scalar_equal(actual: Any, expected: Any) -> bool:
        if isinstance(actual, bool) or isinstance(expected, bool):
            return type(actual) is type(expected) and actual == expected
        if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
            return actual == expected
        return type(actual) is type(expected) and actual == expected

    @staticmethod
    def _finite_condition_scalar(value: Any) -> bool:
        return (
            value is None
            or isinstance(value, (str, bool, int))
            or (isinstance(value, float) and math.isfinite(value))
        )

    @staticmethod
    def _bounded_action_retry_policy(value: Any) -> dict[str, int] | None:
        required = {"max_attempts", "interval_ticks", "timeout_ticks"}
        if not isinstance(value, dict) or set(value) != required:
            return None
        max_attempts = value["max_attempts"]
        interval_ticks = value["interval_ticks"]
        timeout_ticks = value["timeout_ticks"]
        if (
            any(isinstance(item, bool) or not isinstance(item, int) for item in value.values())
            or not 1 <= max_attempts <= ACTION_BEHAVIOR_RETRY_ATTEMPT_LIMIT
            or not 1 <= interval_ticks <= ACTION_BEHAVIOR_DURATION_LIMIT
            or not 1 <= timeout_ticks <= ACTION_BEHAVIOR_DURATION_LIMIT
        ):
            return None
        return {
            "max_attempts": max_attempts,
            "interval_ticks": interval_ticks,
            "timeout_ticks": timeout_ticks,
        }

    def _validated_action_runtime(
        self,
        payload: Any,
        queued_actions: dict[str, ActionIR],
        *,
        require_all: bool,
        snapshot_tick: int,
    ) -> dict[str, dict[str, Any]]:
        if payload is None and not require_all:
            return {action_id: {"retries": {}} for action_id in queued_actions}
        if not isinstance(payload, dict):
            raise RuntimeErrorBase("Snapshot action_runtime must be an object")
        if set(payload) - set(queued_actions):
            raise RuntimeErrorBase("Snapshot action_runtime references non-pending actions")
        if require_all and set(payload) != set(queued_actions):
            raise RuntimeErrorBase("Snapshot action_runtime must cover every pending action")

        validated: dict[str, dict[str, Any]] = {}
        for action_id, action in queued_actions.items():
            raw_record = payload.get(action_id, {"retries": {}})
            if not isinstance(raw_record, dict) or set(raw_record) != {"retries"}:
                raise RuntimeErrorBase("Snapshot action_runtime record is invalid")
            raw_retries = raw_record["retries"]
            if not isinstance(raw_retries, dict):
                raise RuntimeErrorBase("Snapshot action_runtime.retries must be an object")
            if len(raw_retries) > 1:
                raise RuntimeErrorBase("Snapshot action_runtime has multiple active retries")
            behavior = self._action_behavior(action.verb)
            phases = behavior.get("phases", []) if isinstance(behavior, dict) else []
            phase_by_id = {
                phase.get("phase_id"): phase
                for phase in phases
                if isinstance(phase, dict) and isinstance(phase.get("phase_id"), str)
            }
            retries: dict[str, dict[str, Any]] = {}
            for phase_id, retry_state in raw_retries.items():
                if not isinstance(phase_id, str) or phase_id not in phase_by_id:
                    raise RuntimeErrorBase("Snapshot action_runtime phase is invalid")
                phase = phase_by_id[phase_id]
                retry_policy = self._bounded_action_retry_policy(phase.get("retry"))
                if not isinstance(retry_policy, dict) or not isinstance(retry_state, dict):
                    raise RuntimeErrorBase("Snapshot action_runtime retry policy is unavailable")
                required = {
                    "attempts", "first_failure_tick", "timeout_at_tick",
                    "next_retry_tick", "condition_id",
                }
                if set(retry_state) != required:
                    raise RuntimeErrorBase("Snapshot action_runtime retry record is invalid")
                attempts = retry_state["attempts"]
                first_failure_tick = retry_state["first_failure_tick"]
                timeout_at_tick = retry_state["timeout_at_tick"]
                next_retry_tick = retry_state["next_retry_tick"]
                condition_id = retry_state["condition_id"]
                if (
                    isinstance(attempts, bool)
                    or not isinstance(attempts, int)
                    or not 1 <= attempts <= min(
                        ACTION_BEHAVIOR_RETRY_ATTEMPT_LIMIT,
                        retry_policy["max_attempts"],
                    )
                    or any(
                        isinstance(value, bool) or not isinstance(value, int) or value < 0
                        for value in (first_failure_tick, timeout_at_tick, next_retry_tick)
                    )
                    or timeout_at_tick != first_failure_tick + retry_policy["timeout_ticks"]
                    or not first_failure_tick < next_retry_tick <= timeout_at_tick
                    or next_retry_tick <= snapshot_tick
                    or not isinstance(condition_id, str)
                    or condition_id not in {
                        condition.get("condition_id")
                        for condition in phase.get("when", [])
                        if isinstance(condition, dict)
                    }
                ):
                    raise RuntimeErrorBase("Snapshot action_runtime retry values are invalid")
                retries[phase_id] = {
                    "attempts": attempts,
                    "first_failure_tick": first_failure_tick,
                    "timeout_at_tick": timeout_at_tick,
                    "next_retry_tick": next_retry_tick,
                    "condition_id": condition_id,
                }
            validated[action_id] = {"retries": retries}
        return validated

    def save_snapshot(self, path: str | Path) -> None:
        pending_ids = {
            action.action_id for _, _, action in self.scheduler.entries()
        }
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
            "action_runtime": {
                action_id: deepcopy(self.action_runtime.get(action_id, {"retries": {}}))
                for action_id in sorted(pending_ids)
            },
            "event_count": len(self.event_log.events),
        }
        Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def load_snapshot(self, path: str | Path) -> None:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeErrorBase("Snapshot 根資料格式無效")
        snapshot_format = payload.get("format")
        if snapshot_format not in {SNAPSHOT_FORMAT_V1, SNAPSHOT_FORMAT_V2, SNAPSHOT_FORMAT}:
            raise RuntimeErrorBase("不支援的 Snapshot 格式")
        try:
            snapshot_version = int(payload.get("snapshot_version", 1 if snapshot_format == SNAPSHOT_FORMAT_V1 else 0))
        except (TypeError, ValueError) as exc:
            raise RuntimeErrorBase("Snapshot 版本格式無效") from exc
        if snapshot_version < 1 or snapshot_version > SNAPSHOT_VERSION:
            raise RuntimeErrorBase(f"不支援的 Snapshot 版本: {snapshot_version}")
        expected_snapshot_version = {
            SNAPSHOT_FORMAT_V1: 1,
            SNAPSHOT_FORMAT_V2: 2,
            SNAPSHOT_FORMAT: 3,
        }[snapshot_format]
        if snapshot_version != expected_snapshot_version:
            raise RuntimeErrorBase("Snapshot format 與 snapshot_version 不一致")
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
        next_action_runtime = self._validated_action_runtime(
            payload.get("action_runtime"),
            next_actions,
            require_all=snapshot_version >= 3,
            snapshot_tick=next_scheduler.tick,
        )

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
        self.action_runtime = next_action_runtime

    def replay(self, events: Iterable[EventIR]) -> None:
        pending_actions: dict[str, tuple[int, int, ActionIR]] = {}
        pending_action_runtime: dict[str, dict[str, Any]] = {}
        lifecycle_seen = False
        lifecycle_tick = 0
        lifecycle_order = 0
        for event in events:
            if event.event_type == "state.committed":
                for item in event.payload.get("applied", []):
                    self.state.seed(
                        item["owner"], item["namespace"], item["key"],
                        item["value"], item["version"],
                    )
            if event.event_type == "action.scheduled":
                lifecycle_seen = True
                lifecycle_tick = max(lifecycle_tick, event.timestamp_tick)
                try:
                    action = ActionIR.from_dict(event.payload["action"])
                    due_tick = int(event.payload["due_tick"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise RuntimeErrorBase("EventLog action.scheduled 無法重播") from exc
                if due_tick < event.timestamp_tick:
                    raise RuntimeErrorBase("EventLog action.scheduled due_tick 早於排程時間")
                lifecycle_order += 1
                action.status = ActionStatus.SCHEDULED
                pending_actions[action.action_id] = (due_tick, lifecycle_order, action)
                pending_action_runtime[action.action_id] = {"retries": {}}
            elif event.event_type == "action.retry_scheduled":
                action_id = event.payload.get("action_id")
                entry = pending_actions.get(action_id) if isinstance(action_id, str) else None
                if entry is None:
                    raise RuntimeErrorBase("EventLog action.retry_scheduled references no pending action")
                behavior = self._action_behavior(entry[2].verb)
                phases = behavior.get("phases", []) if isinstance(behavior, dict) else []
                phase = next(
                    (
                        item for item in phases
                        if isinstance(item, dict)
                        and item.get("phase_id") == event.payload.get("phase_id")
                    ),
                    None,
                )
                retry_policy = self._bounded_action_retry_policy(
                    phase.get("retry") if isinstance(phase, dict) else None
                )
                try:
                    attempt = int(event.payload["attempt"])
                    max_attempts = int(event.payload["max_attempts"])
                    interval_ticks = int(event.payload["interval_ticks"])
                    first_failure_tick = int(event.payload["first_failure_tick"])
                    retry_at_tick = int(event.payload["retry_at_tick"])
                    timeout_at_tick = int(event.payload["timeout_at_tick"])
                    due_tick = int(event.payload["due_tick"])
                    condition_id = event.payload["condition_id"]
                except (KeyError, TypeError, ValueError) as exc:
                    raise RuntimeErrorBase("EventLog action.retry_scheduled is invalid") from exc
                previous_retry = pending_action_runtime[action_id]["retries"].get(
                    event.payload.get("phase_id")
                )
                active_retry_ids = set(pending_action_runtime[action_id]["retries"])
                if active_retry_ids and event.payload.get("phase_id") not in active_retry_ids:
                    raise RuntimeErrorBase("EventLog action.retry_scheduled overlaps another phase")
                expected_attempt = (
                    previous_retry["attempts"] + 1
                    if isinstance(previous_retry, dict) else 1
                )
                expected_first_failure_tick = (
                    previous_retry["first_failure_tick"]
                    if isinstance(previous_retry, dict) else event.timestamp_tick
                )
                if (
                    not isinstance(retry_policy, dict)
                    or attempt != expected_attempt
                    or max_attempts != retry_policy["max_attempts"]
                    or interval_ticks != retry_policy["interval_ticks"]
                    or not 1 <= attempt <= max_attempts
                    or first_failure_tick != expected_first_failure_tick
                    or retry_at_tick != event.timestamp_tick + interval_ticks
                    or timeout_at_tick != first_failure_tick + retry_policy["timeout_ticks"]
                    or retry_at_tick > timeout_at_tick
                    or due_tick != entry[0] + interval_ticks
                    or not isinstance(condition_id, str)
                    or condition_id not in {
                        condition.get("condition_id")
                        for condition in phase.get("when", [])
                        if isinstance(condition, dict)
                    }
                ):
                    raise RuntimeErrorBase("EventLog action.retry_scheduled violates authored policy")
                lifecycle_seen = True
                lifecycle_tick = max(lifecycle_tick, event.timestamp_tick)
                pending_actions[action_id] = (due_tick, entry[1], entry[2])
                pending_action_runtime[action_id]["retries"][phase["phase_id"]] = {
                    "attempts": attempt,
                    "first_failure_tick": first_failure_tick,
                    "timeout_at_tick": timeout_at_tick,
                    "next_retry_tick": retry_at_tick,
                    "condition_id": condition_id,
                }
            elif event.event_type == "action.progressed":
                lifecycle_seen = True
                lifecycle_tick = max(lifecycle_tick, event.timestamp_tick)
                action_id = event.payload.get("action_id")
                next_phase_id = event.payload.get("next_phase_id")
                if isinstance(action_id, str) and isinstance(next_phase_id, str):
                    pending_action_runtime.get(action_id, {}).get("retries", {}).pop(
                        next_phase_id, None
                    )
            elif event.event_type in {
                "action.completed", "action.cancelled", "action.interrupted", "action.failed",
            }:
                action_id = event.payload.get("action_id")
                if isinstance(action_id, str):
                    lifecycle_seen = True
                    lifecycle_tick = max(lifecycle_tick, event.timestamp_tick)
                    pending_actions.pop(action_id, None)
                    pending_action_runtime.pop(action_id, None)
        if lifecycle_seen:
            self.scheduler.tick = lifecycle_tick
            self.scheduler._counter = lifecycle_order
            self.scheduler._queue = list(pending_actions.values())
            heapq.heapify(self.scheduler._queue)
            self.actions = {
                action.action_id: action for _, _, action in pending_actions.values()
            }
            self.action_runtime = pending_action_runtime

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
