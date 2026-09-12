from __future__ import annotations

import fnmatch
import heapq
import json
import math
import os
import re
from copy import deepcopy
from collections import Counter, defaultdict, deque
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Iterable, Protocol

from .action_behavior import (
    ACTION_BEHAVIOR_BRANCH_LIMIT,
    ACTION_BEHAVIOR_BRANCH_PRIORITY_LIMIT,
    ACTION_BEHAVIOR_CHILD_ARG_FIELDS,
    ACTION_BEHAVIOR_CHILD_ARG_LIMIT,
    ACTION_BEHAVIOR_CHILD_MODULES,
    ACTION_BEHAVIOR_CHILD_REQUIRED_ARGS,
    ACTION_BEHAVIOR_CHILD_TARGET_VERBS,
    ACTION_BEHAVIOR_CONDITION_NAMESPACES,
    ACTION_BEHAVIOR_CONDITION_LIMIT,
    ACTION_BEHAVIOR_CONDITION_OPERATORS,
    ACTION_BEHAVIOR_CONDITION_SUBJECTS,
    ACTION_BEHAVIOR_DURATION_LIMIT,
    ACTION_BEHAVIOR_EXECUTION_MODEL_STATIC_DAG,
    ACTION_BEHAVIOR_INTERRUPT_EVENTS,
    ACTION_BEHAVIOR_RETRY_ATTEMPT_LIMIT,
)
from .models import (
    ActionIR, ActionReceipt, ActionStatus, Entity, EventIR, ModuleContract,
    StateCell, StateDelta, TransitionResult, new_id,
)
from .functions import FunctionRegistry
from .player_generation import (
    GeneratedPlayer, actor_id_for_player, generate_character, template_records,
)
from .schema_registry import schema_contracts
from .object_reentry import MODULE_ID as OBJECT_REENTRY_MODULE, SCHEMA_ID as OBJECT_REENTRY_SCHEMA, validate_compiled_grammar
from .state_machine import (
    state_machine_is_active_leaf,
    state_machine_resolve_leaf,
    state_machine_state_matches,
    validate_compiled_state_machines,
)


class RuntimeErrorBase(RuntimeError):
    pass


class KernelTransactionError(RuntimeErrorBase):
    """Durable Kernel state/event commit failed and was rolled back locally."""

    pass


SNAPSHOT_FORMAT_V1 = "compilableworld.snapshot/v0.1"
SNAPSHOT_FORMAT_V2 = "compilableworld.snapshot/v0.2"
SNAPSHOT_FORMAT_V3 = "compilableworld.snapshot/v0.3"
SNAPSHOT_FORMAT_V4 = "compilableworld.snapshot/v0.4"
SNAPSHOT_FORMAT_V5 = "compilableworld.snapshot/v0.5"
SNAPSHOT_FORMAT = "compilableworld.snapshot/v0.6"
SNAPSHOT_VERSION = 6
EVENT_CASCADE_LIMIT = 4096


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
    """Synchronous FIFO EventIR dispatcher with one bounded root cascade.

    Re-entrant publications are queued behind events that were already
    committed.  This preserves batch/EventLog order and prevents a reaction
    chain from growing the Python call stack.  A halted cascade never dispatches
    the remaining queued events; the Runtime records the boundary separately.
    """

    def __init__(
        self,
        max_events_per_cascade: int = EVENT_CASCADE_LIMIT,
        on_halt: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._subscribers: dict[str, list[Callable[[EventIR], None]]] = defaultdict(list)
        self._queue: deque[EventIR] = deque()
        self._dispatching = False
        self.max_events_per_cascade = max_events_per_cascade
        self._on_halt = on_halt
        self.halt_count = 0
        self.last_cascade: dict[str, Any] | None = None

    @property
    def max_events_per_cascade(self) -> int:
        return self._max_events_per_cascade

    @max_events_per_cascade.setter
    def max_events_per_cascade(self, value: int) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError("max_events_per_cascade must be a positive integer")
        self._max_events_per_cascade = value

    def subscribe(self, event_pattern: str, callback: Callable[[EventIR], None]) -> None:
        self._subscribers[event_pattern].append(callback)

    def publish(self, event: EventIR) -> None:
        self.publish_batch([event])

    def publish_batch(self, events: Iterable[EventIR]) -> None:
        batch = list(events)
        if not batch:
            return
        self._queue.extend(batch)
        if self._dispatching:
            return

        root = self._queue[0]
        processed = 0
        last_event: EventIR | None = None
        self._dispatching = True
        try:
            while self._queue and processed < self.max_events_per_cascade:
                event = self._queue.popleft()
                last_event = event
                processed += 1
                for pattern, callbacks in tuple(self._subscribers.items()):
                    if fnmatch.fnmatch(event.event_type, pattern):
                        for callback in tuple(callbacks):
                            callback(event)
            if self._queue:
                first_undispatched = self._queue[0]
                halted = {
                    "halted": True,
                    "reason": "event_cascade_limit",
                    "limit": self.max_events_per_cascade,
                    "dispatched_events": processed,
                    "undispatched_events": len(self._queue),
                    "root_event_id": root.event_id,
                    "root_event_type": root.event_type,
                    "root_correlation_id": root.correlation_id,
                    "last_dispatched_event_id": last_event.event_id if last_event else None,
                    "last_dispatched_event_type": last_event.event_type if last_event else None,
                    "first_undispatched_event_id": first_undispatched.event_id,
                    "first_undispatched_event_type": first_undispatched.event_type,
                }
                self._queue.clear()
                self.halt_count += 1
                self.last_cascade = halted
                if self._on_halt is not None:
                    self._on_halt(dict(halted))
            else:
                self.last_cascade = {
                    "halted": False,
                    "limit": self.max_events_per_cascade,
                    "dispatched_events": processed,
                    "undispatched_events": 0,
                    "root_event_id": root.event_id,
                    "root_event_type": root.event_type,
                    "root_correlation_id": root.correlation_id,
                    "last_dispatched_event_id": last_event.event_id if last_event else None,
                    "last_dispatched_event_type": last_event.event_type if last_event else None,
                }
        except Exception:
            self._queue.clear()
            raise
        finally:
            self._dispatching = False

    def diagnostics(self) -> dict[str, Any]:
        return {
            "max_events_per_cascade": self.max_events_per_cascade,
            "dispatching": self._dispatching,
            "queued_events": len(self._queue),
            "halt_count": self.halt_count,
            "last_cascade": deepcopy(self.last_cascade),
        }


class EventLog:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else None
        self.events: list[EventIR] = []
        self._event_ids: set[str] = set()
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
        self._event_ids = seen_ids

    def append(self, event: EventIR) -> None:
        self.append_batch([event])

    def append_batch(self, events: Iterable[EventIR]) -> None:
        batch = list(events)
        if not batch:
            return
        batch_ids: set[str] = set()
        for event in batch:
            if (
                not isinstance(event, EventIR)
                or not isinstance(event.event_id, str)
                or not event.event_id
                or not isinstance(event.payload, dict)
            ):
                raise KernelTransactionError("EventLog event is invalid")
            if event.event_id in self._event_ids or event.event_id in batch_ids:
                raise KernelTransactionError(
                    f"EventLog contains duplicate event_id: {event.event_id}"
                )
            batch_ids.add(event.event_id)
        encoded = "".join(json.dumps(event.to_dict(), ensure_ascii=False) + "\n" for event in batch)
        if self.path is None:
            self.events.extend(batch)
            self._event_ids.update(batch_ids)
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
        self._event_ids.update(batch_ids)


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
        self.event_log = EventLog(event_log_path)
        self.scheduler = Scheduler()
        self.modules: dict[str, RuntimeModule] = {}
        self.actions: dict[str, ActionIR] = {}
        self.action_runtime: dict[str, dict[str, Any]] = {}
        self.metrics: Counter[str] = Counter()
        self.events = EventBus(on_halt=self._record_event_cascade_halt)
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
        try:
            package = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeErrorBase("Runtime Package 無法讀取或不是有效 JSON") from exc
        cls._validate_runtime_package(package)
        if cls is WorldRuntime and "object_reentry" in package:
            # The validated package explicitly requires the create-only capability.
            from .entity_transaction import EntityTransactionRuntime
            return EntityTransactionRuntime(package, event_log_path)
        return cls(package, event_log_path)

    @staticmethod
    def _validate_runtime_package(package: Any) -> None:
        required = {
            "format", "manifest", "world", "rooms", "exits", "entities",
            "action_behaviors", "state_machines", "quests", "narrative",
            "dialogues", "scenarios", "functions", "player_templates",
            "initial_state", "schema_contracts", "source_checksums",
        }
        allowed = required | {"studio", "object_reentry"}
        if (
            not isinstance(package, dict)
            or set(package) - allowed
            or required - set(package)
            or package.get("format") != "compilableworld.runtime-package/v0.1"
        ):
            raise RuntimeErrorBase("Runtime Package 根契約無效")
        for key in (
            "rooms", "exits", "entities", "action_behaviors", "state_machines",
            "quests", "player_templates", "initial_state",
        ):
            if not isinstance(package.get(key), list):
                raise RuntimeErrorBase(f"Runtime Package {key} 型別無效")
        for key in (
            "manifest", "world", "narrative", "dialogues", "scenarios", "functions",
            "schema_contracts", "source_checksums",
        ):
            if not isinstance(package.get(key), dict):
                raise RuntimeErrorBase(f"Runtime Package {key} 型別無效")
        manifest = package["manifest"]
        manifest_required = {
            "world_id", "world_version", "schema_version", "namespace",
            "runtime_version", "modules",
        }
        if manifest_required - set(manifest):
            raise RuntimeErrorBase("Runtime Package manifest 缺少必要欄位")
        if any(
            not isinstance(manifest.get(key), str) or not manifest[key]
            for key in (
                "world_id", "world_version", "schema_version", "namespace", "runtime_version",
            )
        ):
            raise RuntimeErrorBase("Runtime Package manifest 文字欄位無效")
        modules = manifest.get("modules")
        if (
            not isinstance(modules, list)
            or not modules
            or len(modules) != len(set(modules))
            or any(not isinstance(module_id, str) or not module_id for module_id in modules)
        ):
            raise RuntimeErrorBase("Runtime Package manifest.modules 無效")
        has_object_reentry = "object_reentry" in package
        if has_object_reentry != (OBJECT_REENTRY_MODULE in modules):
            raise RuntimeErrorBase("Runtime Package object_reentry module/source binding mismatch")
        if package.get("schema_contracts") != schema_contracts(include=("object_reentry",) if has_object_reentry else ()):
            raise RuntimeErrorBase("Runtime Package schema_contracts 不完整或版本不符")
        checksums = package["source_checksums"]
        if not checksums or any(
            not isinstance(source, str)
            or not source
            or not isinstance(digest, str)
            or re.fullmatch(r"[a-f0-9]{64}", digest) is None
            for source, digest in checksums.items()
        ):
            raise RuntimeErrorBase("Runtime Package source_checksums 無效")
        if has_object_reentry:
            try:
                validate_compiled_grammar(package["object_reentry"], checksums)
                if manifest.get("source_schemas", {}).get("object_reentry") != OBJECT_REENTRY_SCHEMA:
                    raise ValueError("object_reentry source schema mismatch")
            except (ValueError, TypeError, AttributeError) as exc:
                raise RuntimeErrorBase(f"Runtime Package object_reentry invalid: {exc}") from exc
        try:
            room_ids = {
                room["room_id"] for room in package["rooms"]
                if isinstance(room, dict) and isinstance(room.get("room_id"), str)
            }
            region_ids = {
                room["region"] for room in package["rooms"]
                if isinstance(room, dict) and isinstance(room.get("region"), str)
            }
            entity_ids = {
                entity["entity_id"] for entity in package["entities"]
                if isinstance(entity, dict) and isinstance(entity.get("entity_id"), str)
            }
        except (KeyError, TypeError) as exc:
            raise RuntimeErrorBase("Runtime Package world identity records 無效") from exc
        if (
            len(room_ids) != len(package["rooms"])
            or len(entity_ids) != len(package["entities"])
        ):
            raise RuntimeErrorBase("Runtime Package rooms/entities ID 無效或重複")
        dialogue_source = package["dialogues"]
        if set(dialogue_source) - {"dialogues", "topic_aliases"}:
            raise RuntimeErrorBase("Runtime Package dialogues 含未知欄位")
        dialogue_entries = dialogue_source.get("dialogues")
        topic_aliases = dialogue_source.get("topic_aliases", {})
        if not isinstance(dialogue_entries, list) or not isinstance(topic_aliases, dict):
            raise RuntimeErrorBase("Runtime Package dialogues 型別無效")
        known_topics = {
            entry.get("topic")
            for entry in dialogue_entries
            if isinstance(entry, dict) and isinstance(entry.get("topic"), str)
        }
        if len(topic_aliases) > 64 or any(
            not isinstance(alias, str)
            or not alias
            or alias != alias.strip().lower()
            or len(alias) > 64
            or not isinstance(topic, str)
            or topic not in known_topics
            for alias, topic in topic_aliases.items()
        ):
            raise RuntimeErrorBase("Runtime Package dialogues.topic_aliases 無效")
        try:
            validate_compiled_state_machines(
                package["state_machines"],
                world_id=manifest["world_id"],
                region_ids=region_ids,
                room_ids=room_ids,
                entity_ids=entity_ids,
                enabled_modules=set(modules),
            )
        except ValueError as exc:
            raise RuntimeErrorBase(f"Runtime Package StateIR 無效: {exc}") from exc

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
            {
                "item_id": entity.entity_id,
                "carrier_version": self.state.version(
                    entity.entity_id, "inventory", "carrier",
                ),
            }
            for entity in self.registry.values()
            if entity.entity_id not in replacement_ids
            and self.state.get(entity.entity_id, "inventory", "carrier") in replacement_ids
        ]
        if self.registry.contains(candidate) and candidate not in replacement_ids:
            raise RuntimeErrorBase(f"player actor id already exists: {candidate}")
        spawn = self.package.get("world", {}).get("player_spawn")
        if not spawn:
            raise RuntimeErrorBase("world.player_spawn is required for generated players")
        entity = Entity(
            entity_id=candidate,
            entity_type="character",
            name=profile.name,
            components=["position", "health", "inventory", "quest", "combatant", "magic"],
            metadata={"provenance": "player_generated", "generation": profile.to_dict()},
        )
        materialized = EventIR(
            "player.materialized",
            "kernel",
            {
                "actor_id": candidate,
                "entity": asdict(entity),
                "profile": profile.to_dict(),
                "replaced_actor_ids": sorted(
                    actor_id for actor_id in replacement_ids
                    if actor_id != candidate and self.registry.contains(actor_id)
                ),
                "transferred_items": sorted(
                    carried_items, key=lambda item: item["item_id"],
                ),
            },
            target=candidate,
            timestamp_tick=self.scheduler.tick,
            visibility="private",
        )
        materialized.correlation_id = materialized.event_id

        # Player generation is authoritative Runtime state, so its durable
        # EventLog record and the in-memory materialization succeed or roll
        # back together.  Without this root event, Snapshot can restore a
        # generated actor while EventLog Replay silently loses its registry,
        # profile, and active-player provenance.
        before_entities = dict(self.registry._entities)
        before_cells = dict(self.state._cells)
        before_dynamic = set(self.dynamic_entities)
        before_profiles = deepcopy(self.player_profiles)
        before_active = self.active_player_id
        try:
            self._apply_player_materialized_event(materialized)
            self.event_log.append(materialized)
        except Exception:
            self.registry._entities = before_entities
            self.state._cells = before_cells
            self.dynamic_entities = before_dynamic
            self.player_profiles = before_profiles
            self.active_player_id = before_active
            raise
        return candidate

    def _generated_profile_from_record(self, record: Any) -> GeneratedPlayer:
        """Rebuild and verify one deterministic generated-player record."""
        if not isinstance(record, dict):
            raise RuntimeErrorBase("EventLog player.materialized profile is invalid")
        try:
            mode = record["mode"]
            overrides = (
                record.get("formula", {}).get("override_attributes", {})
                if mode == "custom" else None
            )
            candidates = [
                generate_character(
                    template_id=record["template_id"],
                    name=record["name"],
                    seed=record["seed"],
                    randomize=mode == "random",
                    attribute_overrides=overrides,
                    package=package,
                )
                for package in (self.package, None)
            ]
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeErrorBase(
                "EventLog player.materialized profile is invalid"
            ) from exc
        expected = next(
            (candidate for candidate in candidates if record == candidate.to_dict()),
            None,
        )
        if mode not in {"template", "random", "custom"} or expected is None:
            raise RuntimeErrorBase(
                "EventLog player.materialized profile is not reproducible"
            )
        return expected

    def _apply_player_materialized_event(self, event: EventIR) -> None:
        """Validate and apply the durable root event for a generated actor."""
        payload = event.payload
        required_fields = {
            "actor_id", "entity", "profile", "replaced_actor_ids", "transferred_items",
        }
        actor_id = payload.get("actor_id")
        if (
            event.source != "kernel"
            or event.authority != "runtime"
            or event.visibility != "private"
            or event.target != actor_id
            or event.causation_id is not None
            or event.correlation_id != event.event_id
            or set(payload) != required_fields
            or not isinstance(actor_id, str)
            or re.fullmatch(r"[a-z][a-z0-9_.-]*", actor_id) is None
        ):
            raise RuntimeErrorBase("EventLog player.materialized envelope is invalid")

        profile = self._generated_profile_from_record(payload.get("profile"))
        expected_entity = Entity(
            entity_id=actor_id,
            entity_type="character",
            name=profile.name,
            components=["position", "health", "inventory", "quest", "combatant", "magic"],
            metadata={"provenance": "player_generated", "generation": profile.to_dict()},
        )
        if payload.get("entity") != asdict(expected_entity):
            raise RuntimeErrorBase("EventLog player.materialized entity is invalid")

        replacement_ids = payload.get("replaced_actor_ids")
        transferred_items = payload.get("transferred_items")
        if (
            not isinstance(replacement_ids, list)
            or replacement_ids != sorted(replacement_ids)
            or len(replacement_ids) != len(set(replacement_ids))
            or any(not isinstance(item, str) or item == actor_id for item in replacement_ids)
            or not isinstance(transferred_items, list)
        ):
            raise RuntimeErrorBase("EventLog player.materialized replacement data is invalid")

        default_actor = self.package.get("world", {}).get("default_player_entity")
        allowed_replacements = set(self.dynamic_entities)
        if isinstance(default_actor, str):
            allowed_replacements.add(default_actor)
        if any(
            old_id not in allowed_replacements or not self.registry.contains(old_id)
            for old_id in replacement_ids
        ):
            raise RuntimeErrorBase("EventLog player.materialized replacement actor is invalid")
        if self.registry.contains(actor_id) or any(
            path.startswith(f"{actor_id}::") for path in self.state._cells
        ):
            raise RuntimeErrorBase("EventLog player.materialized actor already exists")

        expected_transfers = sorted(
            (
                {
                    "item_id": entity.entity_id,
                    "carrier_version": self.state.version(
                        entity.entity_id, "inventory", "carrier",
                    ),
                }
                for entity in self.registry.values()
                if entity.entity_id not in replacement_ids
                and self.state.get(entity.entity_id, "inventory", "carrier")
                in replacement_ids
            ),
            key=lambda item: item["item_id"],
        )
        if transferred_items != expected_transfers:
            raise RuntimeErrorBase("EventLog player.materialized transfer data is invalid")

        spawn = self.package.get("world", {}).get("player_spawn")
        if not isinstance(spawn, str) or not spawn:
            raise RuntimeErrorBase("world.player_spawn is required for generated players")
        for old_id in replacement_ids:
            self.registry.remove(old_id)
            self.state.remove_owner(old_id)
            self.dynamic_entities.discard(old_id)
            self.player_profiles.pop(old_id, None)
        self.registry.add(expected_entity)
        self.dynamic_entities.add(actor_id)
        self.player_profiles[actor_id] = profile.to_dict()
        self.active_player_id = actor_id
        self.state.seed(actor_id, "position", "room", spawn)
        for attr, value in profile.attributes.items():
            self.state.seed(actor_id, "combat", attr, value)
        self.state.seed(actor_id, "combat", "phase_tier", profile.phase_tier)
        self.state.seed(actor_id, "health", "current", profile.hp_max)
        self.state.seed(actor_id, "health", "max", profile.hp_max)
        self.state.seed(actor_id, "status", "alive", True)
        self.state.seed(actor_id, "magic", "mp_current", profile.mp_max)
        self.state.seed(actor_id, "magic", "mp_max", profile.mp_max)
        self.state.seed(actor_id, "magic", "fp_current", profile.fp_max)
        self.state.seed(actor_id, "magic", "fp_max", profile.fp_max)
        self.state.seed(actor_id, "wallet", "currency", 0)
        for quest in self.package.get("quests", []):
            self.state.seed(actor_id, "quest", quest["quest_id"], quest["initial_state"])
        for item in transferred_items:
            self.state.seed(
                item["item_id"], "inventory", "carrier", actor_id,
                item["carrier_version"],
            )

    def register_module(self, module: RuntimeModule) -> None:
        contract = module.contract
        if contract.module_id in self.modules:
            raise RuntimeErrorBase(f"重複模組: {contract.module_id}")
        self.modules[contract.module_id] = module
        on_register = getattr(module, "on_register", None)
        if callable(on_register):
            on_register(self)

    def _publish_committed_events(self, events: Iterable[EventIR]) -> None:
        """Dispatch one durable EventLog batch in its recorded FIFO order."""
        batch = list(events)
        for event in batch:
            self.metrics[f"event:{event.event_type}"] += 1
        self.events.publish_batch(batch)

    def _record_event_cascade_halt(self, record: dict[str, Any]) -> None:
        """Persist an audit-only boundary without feeding it back into the bus."""
        event = EventIR(
            event_type="runtime.reaction_halted",
            source="kernel",
            timestamp_tick=self.scheduler.tick,
            causation_id=record.get("last_dispatched_event_id"),
            correlation_id=record.get("root_correlation_id"),
            visibility="audit",
            payload={
                key: value for key, value in record.items()
                if key != "root_correlation_id"
            },
        )
        self.event_log.append(event)
        self.metrics["event_cascades_halted"] += 1
        self.metrics[f"event:{event.event_type}"] += 1

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
        self._publish_committed_events(emitted)
        return applied

    def module_for(self, verb: str) -> RuntimeModule:
        candidates = [m for m in self.modules.values() if verb in m.contract.actions]
        if not candidates:
            raise RuntimeErrorBase(f"這個世界未提供「{verb}」行動；輸入 help 查看目前可用指令")
        if len(candidates) > 1:
            raise RuntimeErrorBase(f"行為 {verb} 的模組設定衝突")
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
            runtime_record = self._new_action_runtime_record(action, behavior)
            scheduler_counter_before = self.scheduler._counter
            entry = self.scheduler.schedule(action, delay)
            self.action_runtime[action.action_id] = runtime_record
            event = self._action_lifecycle_event("action.scheduled", action, behavior, due_tick=entry[0])
            try:
                self.event_log.append(event)
            except KernelTransactionError:
                self.scheduler.remove(action.action_id)
                self.scheduler._counter = scheduler_counter_before
                self.actions.pop(action.action_id, None)
                self.action_runtime.pop(action.action_id, None)
                action.status = ActionStatus.PARSED
                raise
            self._publish_committed_events([event])
            self.metrics["actions_scheduled"] += 1
            title = behavior["title"] if behavior else action.verb
            return ActionReceipt(
                action.action_id, action.status,
                f"{title} 已排程，將於 {delay} tick 後完成（action_id={action.action_id}）",
                [event.event_id],
            )
        return self._execute(action)

    def _execute(self, action: ActionIR) -> ActionReceipt:
        was_scheduled = action.status == ActionStatus.SCHEDULED
        scheduled_behavior = self._action_behavior(action.verb) if was_scheduled else None
        started_event = (
            self._action_lifecycle_event("action.started", action, scheduled_behavior)
            if was_scheduled else None
        )
        state_before = deepcopy(self.state.export())
        try:
            module = self.module_for(action.verb)
            action.status = ActionStatus.VALIDATED
            action.status = ActionStatus.EXECUTING
            result = module.evaluate(action, self)
            if not result.accepted:
                return self._fail(action, result.message, lifecycle_started=was_scheduled)
            applied = self.state.commit(result.deltas, module.contract.write)
            commit_event = EventIR(
                event_type="state.committed", source=module.contract.module_id,
                target=action.actor_id, causation_id=action.action_id,
                correlation_id=action.correlation_id, timestamp_tick=self.scheduler.tick,
                visibility="audit", payload={"applied": applied},
            )
            completed_event = (
                self._action_lifecycle_event("action.completed", action, scheduled_behavior)
                if was_scheduled else None
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
            return self._fail(action, str(exc), lifecycle_started=was_scheduled)
        action.status = ActionStatus.COMPLETED
        self.action_runtime.pop(action.action_id, None)
        self.metrics["actions_completed"] += 1
        self._publish_committed_events(emitted)
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
            if lifecycle_started else None
        )
        payload = {"verb": action.verb, "reason": message}
        if behavior or lifecycle_started:
            payload.update({
                "action_id": action.action_id,
                "behavior_id": behavior["behavior_id"] if behavior else None,
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
        self._publish_committed_events(emitted)
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

    @staticmethod
    def _is_static_action_route(behavior: Any) -> bool:
        return (
            isinstance(behavior, dict)
            and behavior.get("execution_model")
            == ACTION_BEHAVIOR_EXECUTION_MODEL_STATIC_DAG
        )

    def _new_action_runtime_record(
        self,
        action: ActionIR,
        behavior: dict[str, Any] | None,
    ) -> dict[str, Any]:
        route: dict[str, Any] | None = None
        if self._is_static_action_route(behavior):
            phases = behavior.get("phases")
            entry_phase_id = behavior.get("entry_phase_id")
            phase = next(
                (
                    item for item in phases or []
                    if isinstance(item, dict) and item.get("phase_id") == entry_phase_id
                ),
                None,
            )
            if (
                not isinstance(phases, list)
                or not isinstance(entry_phase_id, str)
                or not isinstance(phase, dict)
                or isinstance(phase.get("duration_ticks"), bool)
                or not isinstance(phase.get("duration_ticks"), int)
            ):
                raise RuntimeErrorBase("compiled static Action route is invalid")
            route = {
                "current_phase_id": entry_phase_id,
                "phase_started_tick": action.proposed_at_tick,
                "phase_due_tick": action.proposed_at_tick + phase["duration_ticks"],
                "elapsed_duration_ticks": 0,
                "visited_phase_ids": [entry_phase_id],
            }
        return {
            "retries": {},
            "completed_steps": [],
            "selected_branches": {},
            "route": route,
        }

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
                    "child_step_id": (
                        phase["child_action"].get("step_id")
                        if isinstance(phase.get("child_action"), dict) else None
                    ),
                    "branches": [
                        {
                            "branch_id": branch["branch_id"],
                            "priority": branch["priority"],
                            "condition_ids": [
                                condition["condition_id"]
                                for condition in branch.get("when", [])
                                if isinstance(condition, dict)
                                and isinstance(condition.get("condition_id"), str)
                            ],
                            "child_step_id": (
                                branch["child_action"].get("step_id")
                                if isinstance(branch.get("child_action"), dict) else None
                            ),
                            "next_phase_id": branch.get("next_phase_id"),
                        }
                        for branch in phase.get("branches", [])
                        if isinstance(branch, dict)
                        and isinstance(branch.get("branch_id"), str)
                        and isinstance(branch.get("priority"), int)
                    ],
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
            runtime_record = self.action_runtime.get(action.action_id, {})
            retry_records = runtime_record.get("retries", {})
            completed_steps = list(
                runtime_record.get("completed_steps", [])
            )
            selected_branches = dict(
                runtime_record.get("selected_branches", {})
            )
            route = runtime_record.get("route")
            visited_phase_ids: list[str] = []
            if self._is_static_action_route(behavior) and isinstance(route, dict):
                started_tick = action.proposed_at_tick
                visited_phase_ids = list(route.get("visited_phase_ids", []))
                current_phase_id = route.get("current_phase_id")
                current_phase = next(
                    (
                        dict(phase) for phase in phases
                        if phase.get("phase_id") == current_phase_id
                    ),
                    None,
                )
                completed_phases = max(0, len(visited_phase_ids) - 1)
                elapsed_duration = route.get("elapsed_duration_ticks", 0)
                phase_started = route.get("phase_started_tick", self.scheduler.tick)
                phase_due = route.get("phase_due_tick", self.scheduler.tick)
                current_duration = (
                    current_phase.get("duration_ticks", 0)
                    if isinstance(current_phase, dict) else 0
                )
                progress = elapsed_duration + min(
                    current_duration,
                    max(0, self.scheduler.tick - phase_started),
                )
                if self.scheduler.tick >= phase_due:
                    progress = elapsed_duration + current_duration
            elif retry_records:
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
                "completed_child_steps": completed_steps,
                "selected_branches": [
                    {"phase_id": phase_id, "branch_id": branch_id}
                    for phase_id, branch_id in selected_branches.items()
                ],
                "execution_model": behavior.get("execution_model") if behavior else None,
                "visited_phase_ids": visited_phase_ids,
                "child_step_count": sum(
                    (
                        phase.get("child_step_id") is not None
                        or any(
                            branch.get("child_step_id") is not None
                            for branch in phase.get("branches", [])
                        )
                    )
                    for phase in phases
                ),
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
        causing_action = self.actions.get(event.causation_id or "")
        for entry in self.scheduler.entries():
            action = entry[2]
            behavior = self._action_behavior(action.verb)
            if (
                action.actor_id == actor_id
                and behavior is not None
                and event.event_type in behavior["interrupt_on"]
                and not (
                    causing_action is not None
                    and causing_action.correlation_id == action.correlation_id
                )
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
        self._publish_committed_events([event])
        self.metrics[f"actions_{status.value}"] += 1
        return ActionReceipt(action.action_id, action.status, reason, [event.event_id])

    def _child_lifecycle_event(
        self,
        event_type: str,
        parent: ActionIR,
        behavior: dict[str, Any],
        phase: dict[str, Any],
        child_spec: dict[str, Any],
        child: ActionIR,
        tick: int,
        *,
        reason: str | None = None,
    ) -> EventIR:
        payload: dict[str, Any] = {
            "parent_action_id": parent.action_id,
            "behavior_id": behavior["behavior_id"],
            "actor": parent.actor_id,
            "phase_id": phase["phase_id"],
            "step_id": child_spec["step_id"],
            "child_action_id": child.action_id,
            "child_verb": child.verb,
            "child_target": child.target_id,
        }
        if reason is not None:
            payload["reason"] = reason
        return EventIR(
            event_type=event_type,
            source="kernel",
            target=parent.actor_id,
            causation_id=parent.action_id,
            correlation_id=parent.correlation_id,
            timestamp_tick=tick,
            visibility="private",
            payload=payload,
        )

    def _action_branch_event(
        self,
        parent: ActionIR,
        behavior: dict[str, Any],
        phase: dict[str, Any],
        branch: dict[str, Any],
        next_phase: dict[str, Any],
        tick: int,
    ) -> EventIR:
        child = branch.get("child_action")
        return EventIR(
            event_type="action.branch_selected",
            source="kernel",
            target=parent.actor_id,
            causation_id=parent.action_id,
            correlation_id=parent.correlation_id,
            timestamp_tick=tick,
            visibility="private",
            payload={
                "action_id": parent.action_id,
                "behavior_id": behavior["behavior_id"],
                "actor": parent.actor_id,
                "verb": parent.verb,
                "phase_id": phase["phase_id"],
                "branch_id": branch["branch_id"],
                "priority": branch["priority"],
                "next_phase_id": next_phase["phase_id"],
                "child_step_id": (
                    child.get("step_id") if isinstance(child, dict) else None
                ),
            },
        )

    def _bounded_action_branches(self, value: Any) -> list[dict[str, Any]] | None:
        if not isinstance(value, list) or not value:
            return None
        if any(not isinstance(branch, dict) for branch in value):
            return None
        legacy_fields = {"branch_id", "priority", "when", "child_action"}
        routed_fields = legacy_fields | {"next_phase_id"}
        field_sets = {
            frozenset(branch) for branch in value if isinstance(branch, dict)
        }
        if len(field_sets) != 1 or field_sets.pop() not in {
            frozenset(legacy_fields), frozenset(routed_fields),
        }:
            return None
        routed = "next_phase_id" in value[0]
        minimum = 1 if routed else 2
        if not minimum <= len(value) <= ACTION_BEHAVIOR_BRANCH_LIMIT:
            return None
        branch_ids: set[str] = set()
        priorities: set[int] = set()
        fallback_priorities: list[int] = []
        conditional_priorities: list[int] = []
        for branch in value:
            branch_id = branch.get("branch_id")
            priority = branch.get("priority")
            conditions = branch.get("when")
            if (
                not isinstance(branch_id, str)
                or not branch_id
                or branch_id in branch_ids
                or isinstance(priority, bool)
                or not isinstance(priority, int)
                or not 0 <= priority <= ACTION_BEHAVIOR_BRANCH_PRIORITY_LIMIT
                or priority in priorities
                or not isinstance(conditions, list)
                or len(conditions) > ACTION_BEHAVIOR_CONDITION_LIMIT
                or (
                    routed
                    and (
                        not isinstance(branch.get("next_phase_id"), str)
                        or not branch["next_phase_id"]
                    )
                )
            ):
                return None
            branch_ids.add(branch_id)
            priorities.add(priority)
            for condition in conditions:
                if (
                    not isinstance(condition, dict)
                    or set(condition) != {
                        "condition_id", "subject", "namespace", "key", "operator", "value",
                    }
                    or not isinstance(condition.get("condition_id"), str)
                    or not condition["condition_id"]
                    or condition.get("subject") not in ACTION_BEHAVIOR_CONDITION_SUBJECTS
                    or condition.get("namespace") not in ACTION_BEHAVIOR_CONDITION_NAMESPACES
                    or not isinstance(condition.get("key"), str)
                    or not condition["key"]
                    or condition.get("operator") not in ACTION_BEHAVIOR_CONDITION_OPERATORS
                    or not self._finite_condition_scalar(condition.get("value"))
                ):
                    return None
            if conditions:
                conditional_priorities.append(priority)
            else:
                fallback_priorities.append(priority)
        if (
            len(fallback_priorities) != 1
            or (
                conditional_priorities
                and fallback_priorities[0] >= min(conditional_priorities)
            )
            or value != sorted(value, key=lambda item: (-item["priority"], item["branch_id"]))
        ):
            return None
        return value

    def _execute_action_child(
        self,
        parent: ActionIR,
        behavior: dict[str, Any],
        phase: dict[str, Any],
        raw: Any,
        tick: int,
    ) -> tuple[list[EventIR], bool, str, ActionIR | None]:
        if raw is None:
            return [], True, "", None
        if not isinstance(raw, dict) or set(raw) != {
            "step_id", "verb", "module_id", "target", "args",
        }:
            return [], False, "compiled child Action contract is invalid", None
        step_id = raw.get("step_id")
        verb = raw.get("verb")
        module_id = raw.get("module_id")
        args = raw.get("args")
        target_spec = raw.get("target")
        if (
            not isinstance(step_id, str)
            or not step_id
            or verb not in ACTION_BEHAVIOR_CHILD_MODULES
            or module_id != ACTION_BEHAVIOR_CHILD_MODULES.get(verb)
            or any(
                isinstance(item, dict) and item.get("verb") == verb
                for item in self.package.get("action_behaviors", [])
            )
            or not isinstance(args, dict)
            or len(args) > ACTION_BEHAVIOR_CHILD_ARG_LIMIT
        ):
            return [], False, "compiled child Action is not a bounded primitive", None
        allowed_args = ACTION_BEHAVIOR_CHILD_ARG_FIELDS[verb]
        required_args = ACTION_BEHAVIOR_CHILD_REQUIRED_ARGS.get(verb, set())
        if set(args) - allowed_args or required_args - set(args):
            return [], False, "compiled child Action args violate the primitive contract", None
        if any(
            not (
                value is None
                or isinstance(value, (str, bool, int))
                or (isinstance(value, float) and math.isfinite(value))
            )
            for value in args.values()
        ):
            return [], False, "compiled child Action args are not finite scalars", None
        if any(
            key in {"direction", "recipient", "spell", "text", "topic"}
            and (not isinstance(value, str) or not value.strip())
            for key, value in args.items()
        ):
            return [], False, "compiled child Action string args are invalid", None

        target_id: str | None = None
        if target_spec is not None:
            if not isinstance(target_spec, dict):
                return [], False, "compiled child Action target is invalid", None
            if target_spec.get("source") == "parent_target" and set(target_spec) == {"source"}:
                target_id = parent.target_id
            elif target_spec.get("source") == "entity" and set(target_spec) == {
                "source", "entity_id",
            }:
                target_id = target_spec.get("entity_id")
            else:
                return [], False, "compiled child Action target is invalid", None
        if verb in ACTION_BEHAVIOR_CHILD_TARGET_VERBS and (
            not isinstance(target_id, str) or not self.registry.contains(target_id)
        ):
            return [], False, f"child Action {step_id} target is unavailable", None
        if verb not in ACTION_BEHAVIOR_CHILD_TARGET_VERBS and target_id is not None:
            return [], False, f"child Action {step_id} forbids a target", None
        recipient = args.get("recipient")
        if verb == "give" and (
            not isinstance(recipient, str) or not self.registry.contains(recipient)
        ):
            return [], False, f"child Action {step_id} recipient is unavailable", None

        child = ActionIR(
            actor_id=parent.actor_id,
            verb=verb,
            target_id=target_id,
            args=deepcopy(args),
            correlation_id=parent.correlation_id,
            authority="runtime",
            proposed_at_tick=tick,
        )
        self.actions[child.action_id] = child
        started = self._child_lifecycle_event(
            "action.child_started", parent, behavior, phase, raw, child, tick,
        )
        state_before = deepcopy(self.state.export())
        try:
            module = self.module_for(verb)
            if module.contract.module_id != module_id:
                raise RuntimeErrorBase(
                    f"child Action module mismatch: {module.contract.module_id} != {module_id}"
                )
            child.status = ActionStatus.VALIDATED
            child.status = ActionStatus.EXECUTING
            result = module.evaluate(child, self)
            if not result.accepted:
                child.status = ActionStatus.FAILED
                failed = self._child_lifecycle_event(
                    "action.child_failed", parent, behavior, phase, raw, child, tick,
                    reason=result.message,
                )
                return [started, failed], False, result.message, child
            applied = self.state.commit(result.deltas, module.contract.write)
            committed = EventIR(
                event_type="state.committed",
                source=module.contract.module_id,
                target=parent.actor_id,
                causation_id=child.action_id,
                correlation_id=parent.correlation_id,
                timestamp_tick=tick,
                visibility="audit",
                payload={"applied": applied},
            )
            child.status = ActionStatus.COMPLETED
            completed = self._child_lifecycle_event(
                "action.child_completed", parent, behavior, phase, raw, child, tick,
            )
            emitted = [started, committed, *result.events, completed]
            for event in emitted[2:-1]:
                event.causation_id = event.causation_id or child.action_id
                event.correlation_id = event.correlation_id or parent.correlation_id
                event.timestamp_tick = tick
            return emitted, True, result.message, child
        except RuntimeErrorBase as exc:
            self.state.import_state(state_before)
            child.status = ActionStatus.FAILED
            failed = self._child_lifecycle_event(
                "action.child_failed", parent, behavior, phase, raw, child, tick,
                reason=str(exc),
            )
            return [started, failed], False, str(exc), child

    def advance(self, ticks: int = 1) -> list[ActionReceipt]:
        receipts: list[ActionReceipt] = []
        for _ in range(max(0, ticks)):
            next_tick = self.scheduler.tick + 1
            state_before = deepcopy(self.state.export())
            queue_before = list(self.scheduler._queue)
            counter_before = self.scheduler._counter
            statuses_before = {
                action.action_id: action.status for _, _, action in queue_before
            }
            action_runtime_before = deepcopy(self.action_runtime)
            actions_before = dict(self.actions)
            previous_tick = self.scheduler.tick
            self.scheduler.tick = next_tick
            try:
                decisions = self._action_checkpoint_decisions(next_tick)
                for events, entry, outcome, _ in decisions:
                    action = entry[2]
                    event = events[-1]
                    if outcome == "progress":
                        retry_state = self.action_runtime.get(action.action_id, {}).get(
                            "retries", {}
                        )
                        retry_state.pop(event.payload["next_phase_id"], None)
                        routed_due_tick = event.payload.get("due_tick")
                        if (
                            isinstance(routed_due_tick, int)
                            and not isinstance(routed_due_tick, bool)
                            and routed_due_tick != entry[0]
                        ):
                            removed = self.scheduler.remove(action.action_id)
                            if removed is None:
                                raise RuntimeErrorBase(
                                    f"routed action is no longer queued: {action.action_id}"
                                )
                            self.scheduler.restore((routed_due_tick, removed[1], action))
                        continue
                    removed = self.scheduler.remove(action.action_id)
                    if removed is None:
                        raise RuntimeErrorBase(
                            f"checkpoint action is no longer queued: {action.action_id}"
                        )
                    if outcome == "retry":
                        self.scheduler.restore((event.payload["due_tick"], removed[1], action))
                        retries = self.action_runtime.setdefault(
                            action.action_id,
                            self._new_action_runtime_record(
                                action, self._action_behavior(action.verb),
                            ),
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
                self.event_log.append_batch(
                    event
                    for events, _, _, _ in decisions
                    for event in events
                )
            except KernelTransactionError:
                self.state.import_state(state_before)
                self.scheduler.tick = previous_tick
                self.scheduler._counter = counter_before
                self.scheduler._queue = queue_before
                heapq.heapify(self.scheduler._queue)
                for _, _, action in queue_before:
                    action.status = statuses_before[action.action_id]
                self.action_runtime = action_runtime_before
                self.actions = actions_before
                raise
            except Exception:
                self.state.import_state(state_before)
                self.scheduler.tick = previous_tick
                self.scheduler._counter = counter_before
                self.scheduler._queue = queue_before
                heapq.heapify(self.scheduler._queue)
                for _, _, action in queue_before:
                    action.status = statuses_before[action.action_id]
                self.action_runtime = action_runtime_before
                self.actions = actions_before
                raise
            for events, entry, outcome, message in decisions:
                action = entry[2]
                if outcome == "failed":
                    self.metrics["actions_failed"] += 1
                    receipts.append(ActionReceipt(
                        action.action_id,
                        action.status,
                        message or "phase or child Action failed",
                        [event.event_id for event in events],
                    ))
                elif outcome == "retry":
                    self.metrics["actions_retried"] += 1
                    receipts.append(ActionReceipt(
                        action.action_id,
                        action.status,
                        message or "phase retry scheduled",
                        [event.event_id for event in events],
                    ))
                for event in events:
                    if event.event_type == "action.child_completed":
                        self.metrics["child_actions_completed"] += 1
                    elif event.event_type == "action.child_failed":
                        self.metrics["child_actions_failed"] += 1
                self._publish_committed_events(events)
            # StateIR timers observe the committed checkpoint state at this
            # tick and run before terminal scheduled Actions. The hook is
            # module-owned and can only commit through StateDelta/EventIR.
            state_machine_module = self.modules.get("state_machine.core")
            advance_timers = getattr(state_machine_module, "advance_timers", None)
            if callable(advance_timers):
                advance_timers(next_tick)
            receipts.extend(self._execute(action) for action in self.scheduler.pop_ready())
        return receipts

    def _action_checkpoint_decisions(
        self, tick: int,
    ) -> list[tuple[list[EventIR], tuple[int, int, ActionIR], str, str | None]]:
        decisions: list[
            tuple[list[EventIR], tuple[int, int, ActionIR], str, str | None]
        ] = []
        for entry in self.scheduler.entries():
            due_tick, _, action = entry
            behavior = self._action_behavior(action.verb)
            phases = behavior.get("phases", []) if isinstance(behavior, dict) else []
            if not isinstance(phases, list) or len(phases) < 2:
                continue
            if self._is_static_action_route(behavior):
                decision = self._static_action_checkpoint_decision(
                    entry, behavior, phases, tick,
                )
                if decision is not None:
                    decisions.append(decision)
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
                events: list[EventIR] = []
                child_spec = phase.get("child_action")
                runtime_record = self.action_runtime.setdefault(
                    action.action_id,
                    self._new_action_runtime_record(action, behavior),
                )
                raw_branches = phase.get("branches") if "branches" in phase else []
                if raw_branches:
                    branches = self._bounded_action_branches(raw_branches)
                    selected_branches = runtime_record.setdefault("selected_branches", {})
                    selected_branch_id = selected_branches.get(phase["phase_id"])
                    selected_branch = next(
                        (
                            branch for branch in branches or []
                            if branch.get("branch_id") == selected_branch_id
                        ),
                        None,
                    ) if isinstance(selected_branch_id, str) else None
                    if selected_branch_id is None and branches is not None:
                        selected_branch = next(
                            (
                                branch for branch in branches
                                if all(
                                    self._action_condition_matches(action, condition)
                                    for condition in branch["when"]
                                )
                            ),
                            None,
                        )
                        if selected_branch is not None:
                            selected_branches[phase["phase_id"]] = selected_branch["branch_id"]
                            events.append(self._action_branch_event(
                                action, behavior, phase, selected_branch, next_phase, tick,
                            ))
                    if selected_branch is None:
                        message = (
                            f"Action {behavior['title']} has no valid branch at phase "
                            f"{phase['title']}"
                        )
                        events.append(EventIR(
                            event_type="action.failed",
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
                                "phase_id": phase["phase_id"],
                                "failure_code": "branch_unresolved",
                                "reason": message,
                            },
                        ))
                        decisions.append((events, entry, "failed", message))
                        continue
                    child_spec = selected_branch.get("child_action")
                step_id = (
                    child_spec.get("step_id") if isinstance(child_spec, dict) else None
                )
                completed_steps = runtime_record.setdefault("completed_steps", [])
                if isinstance(step_id, str) and step_id not in completed_steps:
                    child_events, child_ok, child_message, child = self._execute_action_child(
                        action, behavior, phase, child_spec, tick,
                    )
                    events.extend(child_events)
                    if not child_ok:
                        message = (
                            f"child Action {step_id} failed: {child_message}"
                        )
                        events.append(EventIR(
                            event_type="action.failed",
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
                                "phase_id": phase["phase_id"],
                                "step_id": step_id,
                                "child_action_id": child.action_id if child else None,
                                "child_verb": child.verb if child else child_spec.get("verb"),
                                "failure_code": "child_action_failed",
                                "reason": message,
                            },
                        ))
                        decisions.append((events, entry, "failed", message))
                        continue
                    completed_steps.append(step_id)
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
                                f"{message}; retry {attempt}/{retry_policy['max_attempts']} "
                                f"scheduled for tick {retry_at_tick}"
                            )
                            events.append(EventIR(
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
                            ))
                            decisions.append((events, entry, "retry", retry_message))
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
                    events.append(EventIR(
                        event_type="action.failed",
                        source="kernel",
                        target=action.actor_id,
                        causation_id=action.action_id,
                        correlation_id=action.correlation_id,
                        timestamp_tick=tick,
                        visibility="private",
                        payload=failure_payload,
                    ))
                    decisions.append((events, entry, "failed", message))
                    continue
                events.append(EventIR(
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
                ))
                decisions.append((events, entry, "progress", None))
        return decisions

    def _static_action_checkpoint_decision(
        self,
        entry: tuple[int, int, ActionIR],
        behavior: dict[str, Any],
        phases: list[dict[str, Any]],
        tick: int,
    ) -> tuple[list[EventIR], tuple[int, int, ActionIR], str, str | None] | None:
        """Advance one sticky, single-path cursor through a validated static DAG."""
        due_tick, _, action = entry
        runtime_record = self.action_runtime.get(action.action_id)
        route = runtime_record.get("route") if isinstance(runtime_record, dict) else None
        if not isinstance(route, dict):
            raise RuntimeErrorBase("pending static Action route state is unavailable")
        phase_by_id = {
            phase.get("phase_id"): phase
            for phase in phases
            if isinstance(phase, dict) and isinstance(phase.get("phase_id"), str)
        }
        current_phase_id = route.get("current_phase_id")
        phase = phase_by_id.get(current_phase_id)
        if not isinstance(phase, dict):
            raise RuntimeErrorBase("pending static Action current phase is invalid")
        raw_branches = phase.get("branches")
        if raw_branches == []:
            return None
        branches = self._bounded_action_branches(raw_branches)
        if branches is None or any("next_phase_id" not in branch for branch in branches):
            raise RuntimeErrorBase("compiled static Action branches are invalid")

        active_retries = runtime_record.get("retries", {})
        retry_ticks = {
            retry_state.get("next_retry_tick")
            for retry_state in active_retries.values()
            if isinstance(retry_state, dict)
        }
        if active_retries:
            if tick not in retry_ticks:
                return None
        elif tick != route.get("phase_due_tick"):
            return None

        events: list[EventIR] = []
        selected_branches = runtime_record.setdefault("selected_branches", {})
        selected_branch_id = selected_branches.get(current_phase_id)
        selected_branch = next(
            (
                branch for branch in branches
                if branch.get("branch_id") == selected_branch_id
            ),
            None,
        ) if isinstance(selected_branch_id, str) else None
        if selected_branch_id is None:
            selected_branch = next(
                (
                    branch for branch in branches
                    if all(
                        self._action_condition_matches(action, condition)
                        for condition in branch["when"]
                    )
                ),
                None,
            )
            if selected_branch is not None:
                selected_branches[current_phase_id] = selected_branch["branch_id"]
        next_phase = (
            phase_by_id.get(selected_branch.get("next_phase_id"))
            if isinstance(selected_branch, dict) else None
        )
        if selected_branch is None or not isinstance(next_phase, dict):
            message = (
                f"Action {behavior['title']} has no valid static route at phase "
                f"{phase['title']}"
            )
            events.append(EventIR(
                event_type="action.failed",
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
                    "duration_ticks": behavior["duration_ticks"],
                    "phase_id": phase["phase_id"],
                    "failure_code": "route_unresolved",
                    "reason": message,
                },
            ))
            return events, entry, "failed", message
        if selected_branch_id is None:
            events.append(self._action_branch_event(
                action, behavior, phase, selected_branch, next_phase, tick,
            ))

        child_spec = selected_branch.get("child_action")
        step_id = child_spec.get("step_id") if isinstance(child_spec, dict) else None
        completed_steps = runtime_record.setdefault("completed_steps", [])
        if isinstance(step_id, str) and step_id not in completed_steps:
            child_events, child_ok, child_message, child = self._execute_action_child(
                action, behavior, phase, child_spec, tick,
            )
            events.extend(child_events)
            if not child_ok:
                message = f"child Action {step_id} failed: {child_message}"
                events.append(EventIR(
                    event_type="action.failed",
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
                        "duration_ticks": behavior["duration_ticks"],
                        "phase_id": phase["phase_id"],
                        "step_id": step_id,
                        "child_action_id": child.action_id if child else None,
                        "child_verb": child.verb if child else child_spec.get("verb"),
                        "failure_code": "child_action_failed",
                        "reason": message,
                    },
                ))
                return events, entry, "failed", message
            completed_steps.append(step_id)

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
            retry_state = active_retries.get(next_phase["phase_id"])
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
                        f"{message}; retry {attempt}/{retry_policy['max_attempts']} "
                        f"scheduled for tick {retry_at_tick}"
                    )
                    events.append(EventIR(
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
                            "duration_ticks": behavior["duration_ticks"],
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
                    ))
                    return events, entry, "retry", retry_message
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
                "duration_ticks": behavior["duration_ticks"],
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
            events.append(EventIR(
                event_type="action.failed",
                source="kernel",
                target=action.actor_id,
                causation_id=action.action_id,
                correlation_id=action.correlation_id,
                timestamp_tick=tick,
                visibility="private",
                payload=failure_payload,
            ))
            return events, entry, "failed", message

        elapsed_duration = route.get("elapsed_duration_ticks")
        visited_phase_ids = route.get("visited_phase_ids")
        if (
            isinstance(elapsed_duration, bool)
            or not isinstance(elapsed_duration, int)
            or not isinstance(visited_phase_ids, list)
        ):
            raise RuntimeErrorBase("pending static Action route progress is invalid")
        progress_ticks = elapsed_duration + phase["duration_ticks"]
        next_phase_due_tick = tick + next_phase["duration_ticks"]
        route.update({
            "current_phase_id": next_phase["phase_id"],
            "phase_started_tick": tick,
            "phase_due_tick": next_phase_due_tick,
            "elapsed_duration_ticks": progress_ticks,
            "visited_phase_ids": [*visited_phase_ids, next_phase["phase_id"]],
        })
        progress_payload = {
            "action_id": action.action_id,
            "behavior_id": behavior["behavior_id"],
            "actor": action.actor_id,
            "verb": action.verb,
            "phase_id": phase["phase_id"],
            "phase_title": phase["title"],
            "phase_index": len(visited_phase_ids),
            "completed_phases": len(visited_phase_ids),
            "total_phases": len(phases),
            "next_phase_id": next_phase["phase_id"],
            "progress_ticks": progress_ticks,
            "duration_ticks": behavior["duration_ticks"],
            "phase_due_tick": next_phase_due_tick,
        }
        if next_phase["phase_id"] == behavior.get("terminal_phase_id"):
            progress_payload["due_tick"] = next_phase_due_tick
        events.append(EventIR(
            event_type="action.progressed",
            source="kernel",
            target=action.actor_id,
            causation_id=action.action_id,
            correlation_id=action.correlation_id,
            timestamp_tick=tick,
            visibility="private",
            payload=progress_payload,
        ))
        return events, entry, "progress", None

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
        queued_due_ticks: dict[str, int],
        *,
        require_all: bool,
        snapshot_tick: int,
        snapshot_version: int,
    ) -> dict[str, dict[str, Any]]:
        if payload is None and not require_all:
            return {
                action_id: self._new_action_runtime_record(
                    action, self._action_behavior(action.verb),
                )
                for action_id, action in queued_actions.items()
            }
        if not isinstance(payload, dict):
            raise RuntimeErrorBase("Snapshot action_runtime must be an object")
        if set(payload) - set(queued_actions):
            raise RuntimeErrorBase("Snapshot action_runtime references non-pending actions")
        if require_all and set(payload) != set(queued_actions):
            raise RuntimeErrorBase("Snapshot action_runtime must cover every pending action")

        validated: dict[str, dict[str, Any]] = {}
        for action_id, action in queued_actions.items():
            raw_record = payload.get(action_id, {"retries": {}})
            if snapshot_version >= 6:
                expected_fields = {
                    "retries", "completed_steps", "selected_branches", "route",
                }
            elif snapshot_version >= 5:
                expected_fields = {"retries", "completed_steps", "selected_branches"}
            elif snapshot_version >= 4:
                expected_fields = {"retries", "completed_steps"}
            else:
                expected_fields = {"retries"}
            if not isinstance(raw_record, dict) or set(raw_record) != expected_fields:
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
            static_route = self._is_static_action_route(behavior)
            raw_route = raw_record.get("route")
            route: dict[str, Any] | None = None
            if static_route:
                if snapshot_version < 6:
                    raise RuntimeErrorBase(
                        "Snapshot version predates pending static Action route state"
                    )
                route_fields = {
                    "current_phase_id", "phase_started_tick", "phase_due_tick",
                    "elapsed_duration_ticks", "visited_phase_ids",
                }
                if not isinstance(raw_route, dict) or set(raw_route) != route_fields:
                    raise RuntimeErrorBase("Snapshot action_runtime.route is invalid")
                current_phase_id = raw_route["current_phase_id"]
                phase_started_tick = raw_route["phase_started_tick"]
                phase_due_tick = raw_route["phase_due_tick"]
                elapsed_duration_ticks = raw_route["elapsed_duration_ticks"]
                visited_phase_ids = raw_route["visited_phase_ids"]
                current_phase = phase_by_id.get(current_phase_id)
                if (
                    not isinstance(current_phase_id, str)
                    or not isinstance(current_phase, dict)
                    or any(
                        isinstance(value, bool) or not isinstance(value, int) or value < 0
                        for value in (
                            phase_started_tick, phase_due_tick, elapsed_duration_ticks,
                        )
                    )
                    or not isinstance(visited_phase_ids, list)
                    or not visited_phase_ids
                    or any(
                        not isinstance(phase_id, str) or phase_id not in phase_by_id
                        for phase_id in visited_phase_ids
                    )
                    or len(visited_phase_ids) != len(set(visited_phase_ids))
                    or visited_phase_ids[0] != behavior.get("entry_phase_id")
                    or visited_phase_ids[-1] != current_phase_id
                    or phase_started_tick > snapshot_tick
                    or (raw_retries and phase_due_tick > snapshot_tick)
                    or (not raw_retries and phase_due_tick <= snapshot_tick)
                    or phase_due_tick
                    != phase_started_tick + current_phase["duration_ticks"]
                    or elapsed_duration_ticks != sum(
                        phase_by_id[phase_id]["duration_ticks"]
                        for phase_id in visited_phase_ids[:-1]
                    )
                ):
                    raise RuntimeErrorBase("Snapshot action_runtime.route values are invalid")
                route = {
                    "current_phase_id": current_phase_id,
                    "phase_started_tick": phase_started_tick,
                    "phase_due_tick": phase_due_tick,
                    "elapsed_duration_ticks": elapsed_duration_ticks,
                    "visited_phase_ids": list(visited_phase_ids),
                }
                queued_due_tick = queued_due_ticks.get(action_id)
                terminal = current_phase_id == behavior.get("terminal_phase_id")
                if (
                    isinstance(queued_due_tick, bool)
                    or not isinstance(queued_due_tick, int)
                    or queued_due_tick <= snapshot_tick
                    or (terminal and queued_due_tick != phase_due_tick)
                    or (not terminal and queued_due_tick < phase_due_tick)
                ):
                    raise RuntimeErrorBase(
                        "Snapshot action_runtime.route due tick is invalid"
                    )
            elif snapshot_version >= 6 and raw_route is not None:
                raise RuntimeErrorBase(
                    "Snapshot legacy action_runtime.route must be null"
                )
            cumulative_ticks = 0
            earliest_step_ticks: dict[str, int] = {}
            earliest_branch_ticks: dict[str, int] = {}
            branch_phase_ids: list[str] = []
            for phase in phases:
                if not isinstance(phase, dict):
                    continue
                duration_ticks = phase.get("duration_ticks")
                if isinstance(duration_ticks, int) and not isinstance(duration_ticks, bool):
                    cumulative_ticks += duration_ticks
                child_action = phase.get("child_action")
                if isinstance(child_action, dict) and isinstance(
                    child_action.get("step_id"), str
                ):
                    earliest_step_ticks[child_action["step_id"]] = (
                        action.proposed_at_tick + cumulative_ticks
                    )
                raw_branches = phase.get("branches")
                if raw_branches:
                    branches = self._bounded_action_branches(raw_branches)
                    phase_id = phase.get("phase_id")
                    if branches is None or not isinstance(phase_id, str):
                        raise RuntimeErrorBase(
                            "Snapshot action_runtime behavior branches are invalid"
                        )
                    branch_phase_ids.append(phase_id)
                    earliest_branch_ticks[phase_id] = action.proposed_at_tick + cumulative_ticks
                    for branch in branches:
                        branch_child = branch.get("child_action")
                        if isinstance(branch_child, dict) and isinstance(
                            branch_child.get("step_id"), str
                        ):
                            earliest_step_ticks[branch_child["step_id"]] = (
                                action.proposed_at_tick + cumulative_ticks
                            )
            if static_route and route is not None:
                for phase_id in route["visited_phase_ids"]:
                    earliest_branch_ticks[phase_id] = action.proposed_at_tick
                    phase = phase_by_id[phase_id]
                    for branch in self._bounded_action_branches(
                        phase.get("branches")
                    ) or []:
                        branch_child = branch.get("child_action")
                        if isinstance(branch_child, dict) and isinstance(
                            branch_child.get("step_id"), str
                        ):
                            earliest_step_ticks[branch_child["step_id"]] = (
                                action.proposed_at_tick
                            )

            raw_selected_branches = raw_record.get("selected_branches", {})
            if not isinstance(raw_selected_branches, dict) or any(
                not isinstance(phase_id, str) or not isinstance(branch_id, str)
                for phase_id, branch_id in raw_selected_branches.items()
            ):
                raise RuntimeErrorBase(
                    "Snapshot action_runtime.selected_branches must be an object"
                )
            selected_branches: dict[str, str] = {}
            for phase_id, branch_id in raw_selected_branches.items():
                phase = phase_by_id.get(phase_id)
                branches = self._bounded_action_branches(
                    phase.get("branches") if isinstance(phase, dict) else None
                )
                if (
                    branches is None
                    or branch_id not in {branch["branch_id"] for branch in branches}
                    or earliest_branch_ticks.get(phase_id, snapshot_tick + 1) > snapshot_tick
                ):
                    raise RuntimeErrorBase(
                        "Snapshot action_runtime branch selection is invalid"
                    )
                selected_branches[phase_id] = branch_id
            if static_route and route is not None:
                route_phase_ids = route["visited_phase_ids"]
                expected_selected_ids = list(route_phase_ids[:-1])
                current_route_phase = phase_by_id[route_phase_ids[-1]]
                if raw_retries and current_route_phase.get("branches"):
                    expected_selected_ids.append(route_phase_ids[-1])
                if set(selected_branches) != set(expected_selected_ids):
                    raise RuntimeErrorBase(
                        "Snapshot action_runtime branch selections do not match routed path"
                    )
                for source_id, target_id in zip(
                    route_phase_ids[:-1], route_phase_ids[1:], strict=True,
                ):
                    source = phase_by_id[source_id]
                    branches = self._bounded_action_branches(source.get("branches"))
                    selected = next(
                        (
                            branch for branch in branches or []
                            if branch["branch_id"] == selected_branches.get(source_id)
                        ),
                        None,
                    )
                    if selected is None or selected.get("next_phase_id") != target_id:
                        raise RuntimeErrorBase(
                            "Snapshot action_runtime routed path violates branch target"
                        )
                if raw_retries:
                    selected = next(
                        (
                            branch for branch in self._bounded_action_branches(
                                current_route_phase.get("branches")
                            ) or []
                            if branch["branch_id"]
                            == selected_branches.get(route_phase_ids[-1])
                        ),
                        None,
                    )
                    if (
                        selected is None
                        or set(raw_retries) != {selected.get("next_phase_id")}
                    ):
                        raise RuntimeErrorBase(
                            "Snapshot action_runtime retry does not match routed target"
                        )
            else:
                selected_phase_ids = [
                    phase_id for phase_id in branch_phase_ids
                    if phase_id in selected_branches
                ]
                if (
                    set(selected_branches) != set(selected_phase_ids)
                    or selected_phase_ids != branch_phase_ids[:len(selected_phase_ids)]
                ):
                    raise RuntimeErrorBase(
                        "Snapshot action_runtime branch selections are not an authored prefix"
                    )

            authored_steps: list[str] = []
            selected_child_steps: set[str] = set()
            authored_phase_order = (
                [phase_by_id[phase_id] for phase_id in route["visited_phase_ids"]]
                if static_route and route is not None
                else phases
            )
            for phase in authored_phase_order:
                if not isinstance(phase, dict):
                    continue
                child_action = phase.get("child_action")
                if isinstance(child_action, dict) and isinstance(
                    child_action.get("step_id"), str
                ):
                    authored_steps.append(child_action["step_id"])
                branches = self._bounded_action_branches(phase.get("branches"))
                phase_id = phase.get("phase_id")
                selected_branch_id = selected_branches.get(phase_id)
                if branches is not None and selected_branch_id is not None:
                    selected_branch = next(
                        branch for branch in branches
                        if branch["branch_id"] == selected_branch_id
                    )
                    selected_child = selected_branch.get("child_action")
                    if isinstance(selected_child, dict) and isinstance(
                        selected_child.get("step_id"), str
                    ):
                        authored_steps.append(selected_child["step_id"])
                        selected_child_steps.add(selected_child["step_id"])
            raw_completed_steps = raw_record.get("completed_steps", [])
            if (
                not isinstance(raw_completed_steps, list)
                or any(not isinstance(step_id, str) for step_id in raw_completed_steps)
                or len(raw_completed_steps) != len(set(raw_completed_steps))
                or raw_completed_steps != authored_steps[:len(raw_completed_steps)]
                or not selected_child_steps.issubset(set(raw_completed_steps))
                or any(
                    earliest_step_ticks.get(step_id, snapshot_tick + 1) > snapshot_tick
                    for step_id in raw_completed_steps
                )
            ):
                raise RuntimeErrorBase(
                    "Snapshot action_runtime.completed_steps is not an authored prefix"
                )
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
            validated[action_id] = {
                "retries": retries,
                "completed_steps": list(raw_completed_steps),
                "selected_branches": selected_branches,
                "route": route,
            }
        return validated

    def save_snapshot(self, path: str | Path) -> None:
        pending_actions = {
            action.action_id: action for _, _, action in self.scheduler.entries()
        }
        package_entity_ids = {
            raw["entity_id"] for raw in self.package["entities"]
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
            # Dynamic entities are serialized in full below. Package-backed
            # entities only need their live membership recorded so a removed
            # default player is not silently resurrected on load.
            "static_entity_ids": sorted(
                entity_id for entity_id in self.registry._entities
                if entity_id in package_entity_ids
                and entity_id not in self.dynamic_entities
            ),
            "dynamic_entities": [
                asdict(self.registry.get(entity_id)) for entity_id in sorted(self.dynamic_entities)
            ],
            "player_profiles": self.player_profiles,
            "active_player_id": self.active_player_id,
            "scheduler": self.scheduler.export(),
            "action_runtime": {
                action_id: deepcopy(self.action_runtime.get(
                    action_id,
                    self._new_action_runtime_record(
                        pending_actions[action_id],
                        self._action_behavior(pending_actions[action_id].verb),
                    ),
                ))
                for action_id in sorted(pending_actions)
            },
            "event_count": len(self.event_log.events),
        }
        Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def load_snapshot(self, path: str | Path) -> None:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        self._restore_snapshot_payload(payload, record_event=True)

    def _restore_snapshot_payload(
        self,
        payload: Any,
        *,
        record_event: bool,
    ) -> None:
        if not isinstance(payload, dict):
            raise RuntimeErrorBase("Snapshot 根資料格式無效")
        snapshot_format = payload.get("format")
        if snapshot_format not in {
            SNAPSHOT_FORMAT_V1, SNAPSHOT_FORMAT_V2, SNAPSHOT_FORMAT_V3,
            SNAPSHOT_FORMAT_V4, SNAPSHOT_FORMAT_V5, SNAPSHOT_FORMAT,
        }:
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
            SNAPSHOT_FORMAT_V3: 3,
            SNAPSHOT_FORMAT_V4: 4,
            SNAPSHOT_FORMAT_V5: 5,
            SNAPSHOT_FORMAT: 6,
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
        package_entities = {
            raw["entity_id"]: Entity(**raw) for raw in self.package["entities"]
        }
        static_entity_ids = set(package_entities)
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

        static_ids_payload = payload.get("static_entity_ids")
        if static_ids_payload is None:
            # Snapshots written before live static membership was persisted
            # assumed every Package entity still existed. Generated-player
            # snapshots are the supported exception: create_player removes the
            # default actor and its State owner, so infer that tombstone when
            # the older payload contains enough evidence.
            next_static_ids = set(static_entity_ids)
            default_actor = self.package.get("world", {}).get("default_player_entity")
            if (
                active_player_id is not None
                and active_player_id in next_profiles
                and isinstance(default_actor, str)
                and not any(
                    path.startswith(f"{default_actor}::")
                    for path in payload["state"]
                )
            ):
                next_static_ids.discard(default_actor)
        elif (
            not isinstance(static_ids_payload, list)
            or any(
                not isinstance(entity_id, str)
                or entity_id not in static_entity_ids
                for entity_id in static_ids_payload
            )
            or static_ids_payload != sorted(static_ids_payload)
            or len(static_ids_payload) != len(set(static_ids_payload))
        ):
            raise RuntimeErrorBase("Snapshot static_entity_ids is invalid")
        else:
            next_static_ids = set(static_ids_payload)

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
        snapshot_tick = payload.get("tick")
        if (
            isinstance(snapshot_tick, bool)
            or not isinstance(snapshot_tick, int)
            or snapshot_tick < 0
            or snapshot_tick != next_scheduler.tick
        ):
            raise RuntimeErrorBase("Snapshot tick 與 scheduler tick 不一致")
        next_actions = {action.action_id: action for action in queued_actions}
        next_due_ticks = {
            action.action_id: due_tick
            for due_tick, _, action in next_scheduler.entries()
        }
        next_action_runtime = self._validated_action_runtime(
            payload.get("action_runtime"),
            next_actions,
            next_due_ticks,
            require_all=snapshot_version >= 3,
            snapshot_tick=next_scheduler.tick,
            snapshot_version=snapshot_version,
        )

        next_entities = {
            entity_id: package_entities[entity_id]
            for entity_id in next_static_ids
        }
        next_entities.update(snapshot_entities)

        if record_event:
            restored_event = EventIR(
                "snapshot.restored",
                "kernel",
                {"snapshot": deepcopy(payload)},
                target=active_player_id,
                timestamp_tick=next_scheduler.tick,
                visibility="private",
            )
            restored_event.correlation_id = restored_event.event_id
            # The EventLog record and the in-memory restore form one logical
            # transition. Append only after the complete payload is validated,
            # but before touching live Runtime objects, so an append failure
            # leaves the current session unchanged.
            self.event_log.append(restored_event)

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

    def _apply_snapshot_restored_event(self, event: EventIR) -> None:
        """Apply one durable Snapshot restore boundary during EventLog Replay."""
        snapshot = event.payload.get("snapshot")
        if (
            event.source != "kernel"
            or event.authority != "runtime"
            or event.visibility != "private"
            or event.causation_id is not None
            or event.correlation_id != event.event_id
            or set(event.payload) != {"snapshot"}
            or not isinstance(snapshot, dict)
            or event.target != snapshot.get("active_player_id")
            or event.timestamp_tick != snapshot.get("tick")
        ):
            raise RuntimeErrorBase("EventLog snapshot.restored envelope is invalid")
        self._restore_snapshot_payload(deepcopy(snapshot), record_event=False)

    def _validate_replayed_fsm_lifecycle(self, event: EventIR) -> None:
        payload = event.payload
        machine = next((
            item for item in self.package.get("state_machines", [])
            if isinstance(item, dict)
            and item.get("state_machine_id") == payload.get("state_machine_id")
        ), None)
        transition = next((
            item for item in machine.get("transitions", [])
            if isinstance(item, dict)
            and item.get("transition_id") == payload.get("transition_id")
        ), None) if isinstance(machine, dict) else None
        required_fields = {
            "state_machine_id", "title", "owner_scope", "owner_id",
            "transition_id", "from", "to", "trigger",
        }
        leaf_fields = {"from_leaf", "to_leaf"}
        hierarchical_payload = (
            isinstance(machine, dict)
            and "initial_leaf" in machine
            and "hierarchy" in machine
        )
        if hierarchical_payload:
            required_fields.update(leaf_fields)
        payload_has_leaf = leaf_fields.issubset(payload)
        payload_fields_valid = set(payload) == required_fields or (
            not hierarchical_payload
            and set(payload) == required_fields | leaf_fields
        )
        expected_visibility = None
        expected_target = None
        if isinstance(machine, dict):
            visibility = machine.get("visibility")
            expected_visibility = (
                "public" if visibility in {"public", "observable"}
                else "private" if visibility == "private" and machine.get("owner_scope") == "entity"
                else "audit"
            )
            expected_target = (
                machine.get("owner_id") if machine.get("owner_scope") == "entity" else None
            )
        expected_trigger = (
            transition.get("on", "fsm.timer_elapsed")
            if isinstance(transition, dict) else None
        )
        terminal_type = (
            f"fsm.{state_machine_resolve_leaf(machine, transition.get('to'))}"
            if isinstance(machine, dict)
            and isinstance(transition, dict)
            and state_machine_resolve_leaf(machine, transition.get("to"))
            in {"completed", "failed"}
            else None
        )
        if (
            event.source != "state_machine.core"
            or event.authority != "runtime"
            or not payload_fields_valid
            or not isinstance(machine, dict)
            or not isinstance(transition, dict)
            or payload.get("title") != machine.get("title")
            or payload.get("owner_scope") != machine.get("owner_scope")
            or payload.get("owner_id") != machine.get("owner_id")
            or payload.get("from") != transition.get("from")
            or payload.get("to") != transition.get("to")
            or (
                payload_has_leaf
                and (
                    not state_machine_is_active_leaf(machine, payload.get("from_leaf"))
                    or not state_machine_state_matches(
                        machine, transition.get("from"), payload.get("from_leaf"),
                    )
                    or payload.get("to_leaf")
                    != state_machine_resolve_leaf(machine, transition.get("to"))
                )
            )
            or payload.get("trigger") != expected_trigger
            or event.visibility != expected_visibility
            or event.target != expected_target
            or not isinstance(event.causation_id, str)
            or not event.causation_id
            or (
                event.event_type in {"fsm.completed", "fsm.failed"}
                and event.event_type != terminal_type
            )
        ):
            raise RuntimeErrorBase(
                f"EventLog {event.event_type} violates authored StateIR lifecycle"
            )

    def _validate_replay_support(self, events: list[EventIR]) -> None:
        if any(event.event_type == "entity.committed" for event in events):
            raise RuntimeErrorBase("entity.committed Replay requires EntityTransactionRuntime")

    def _apply_replayed_entity_commit(self, event: EventIR, previous: EventIR | None) -> None:
        raise RuntimeErrorBase("entity.committed Replay requires EntityTransactionRuntime")

    def replay(self, events: Iterable[EventIR]) -> None:
        events = list(events)
        self._validate_replay_support(events)
        pending_actions: dict[str, tuple[int, int, ActionIR]] = {}
        pending_action_runtime: dict[str, dict[str, Any]] = {}
        lifecycle_seen = False
        lifecycle_order = 0
        replay_tick = self.scheduler.tick
        previous_event: EventIR | None = None
        for event in events:
            preceding_event = previous_event
            previous_event = event
            if (
                isinstance(event.timestamp_tick, bool)
                or not isinstance(event.timestamp_tick, int)
                or event.timestamp_tick < 0
            ):
                raise RuntimeErrorBase("EventLog timestamp_tick is invalid")
            if event.event_type == "snapshot.restored":
                self._apply_snapshot_restored_event(event)
                pending_actions = {
                    action.action_id: (due_tick, order, action)
                    for due_tick, order, action in self.scheduler.entries()
                }
                pending_action_runtime = deepcopy(self.action_runtime)
                lifecycle_order = self.scheduler._counter
                lifecycle_seen = True
                replay_tick = self.scheduler.tick
                continue
            replay_tick = max(replay_tick, event.timestamp_tick)
            if event.event_type in {"fsm.transitioned", "fsm.completed", "fsm.failed"}:
                self._validate_replayed_fsm_lifecycle(event)
            if event.event_type == "player.materialized":
                self._apply_player_materialized_event(event)
            if event.event_type == "entity.committed":
                self._apply_replayed_entity_commit(event, preceding_event)
            if event.event_type == "state.committed":
                for item in event.payload.get("applied", []):
                    self.state.seed(
                        item["owner"], item["namespace"], item["key"],
                        item["value"], item["version"],
                    )
            if event.event_type == "fsm.timer_elapsed":
                payload = event.payload
                machine_id = payload.get("state_machine_id")
                transition_id = payload.get("transition_id")
                machine = next((
                    item for item in self.package.get("state_machines", [])
                    if isinstance(item, dict)
                    and item.get("state_machine_id") == machine_id
                ), None)
                transition = next((
                    item for item in machine.get("transitions", [])
                    if isinstance(item, dict)
                    and item.get("transition_id") == transition_id
                ), None) if isinstance(machine, dict) else None
                after_ticks = payload.get("after_ticks")
                entered_tick = payload.get("entered_tick")
                eligible_at_tick = payload.get("eligible_at_tick")
                fired_at_tick = payload.get("fired_at_tick")
                timer_leaf_fields = {"from_leaf", "to_leaf"}
                timer_payload_has_leaf = timer_leaf_fields.issubset(payload)
                timer_payload_has_partial_leaf = bool(
                    timer_leaf_fields.intersection(payload)
                ) and not timer_payload_has_leaf
                timer_requires_leaf = (
                    isinstance(machine, dict)
                    and "initial_leaf" in machine
                    and "hierarchy" in machine
                )
                if (
                    event.source != "state_machine.core"
                    or not isinstance(machine_id, str)
                    or not isinstance(transition_id, str)
                    or not isinstance(machine, dict)
                    or not isinstance(transition, dict)
                    or isinstance(after_ticks, bool)
                    or not isinstance(after_ticks, int)
                    or isinstance(entered_tick, bool)
                    or not isinstance(entered_tick, int)
                    or isinstance(eligible_at_tick, bool)
                    or not isinstance(eligible_at_tick, int)
                    or isinstance(fired_at_tick, bool)
                    or not isinstance(fired_at_tick, int)
                    or after_ticks != transition.get("after_ticks")
                    or entered_tick < 0
                    or eligible_at_tick != entered_tick + after_ticks
                    or fired_at_tick != event.timestamp_tick
                    or fired_at_tick < eligible_at_tick
                    or payload.get("owner_id") != machine.get("owner_id")
                    or payload.get("owner_scope") != machine.get("owner_scope")
                    or payload.get("title") != machine.get("title")
                    or payload.get("from") != transition.get("from")
                    or payload.get("to") != transition.get("to")
                    or timer_payload_has_partial_leaf
                    or (timer_requires_leaf and not timer_payload_has_leaf)
                    or (
                        timer_payload_has_leaf
                        and (
                            not state_machine_is_active_leaf(
                                machine, payload.get("from_leaf"),
                            )
                            or not state_machine_state_matches(
                                machine, transition.get("from"),
                                payload.get("from_leaf"),
                            )
                            or payload.get("to_leaf")
                            != state_machine_resolve_leaf(
                                machine, transition.get("to"),
                            )
                        )
                    )
                    or payload.get("trigger") != "fsm.timer_elapsed"
                    or event.causation_id is not None
                    or event.correlation_id != event.event_id
                ):
                    raise RuntimeErrorBase("EventLog fsm.timer_elapsed violates authored timer")
                lifecycle_seen = True
            if event.event_type == "runtime.reaction_halted":
                payload = event.payload
                required_fields = {
                    "halted", "reason", "limit", "dispatched_events", "undispatched_events",
                    "root_event_id", "root_event_type", "last_dispatched_event_id",
                    "last_dispatched_event_type", "first_undispatched_event_id",
                    "first_undispatched_event_type",
                }
                required_strings = {
                    "reason", "root_event_id", "root_event_type",
                    "last_dispatched_event_id", "last_dispatched_event_type",
                    "first_undispatched_event_id", "first_undispatched_event_type",
                }
                required_ints = {"limit", "dispatched_events", "undispatched_events"}
                if (
                    event.source != "kernel"
                    or event.visibility != "audit"
                    or event.target is not None
                    or set(payload) != required_fields
                    or isinstance(event.timestamp_tick, bool)
                    or not isinstance(event.timestamp_tick, int)
                    or event.timestamp_tick < 0
                    or payload.get("halted") is not True
                    or payload.get("reason") != "event_cascade_limit"
                    or any(
                        not isinstance(payload.get(key), str) or not payload[key]
                        for key in required_strings
                    )
                    or any(
                        isinstance(payload.get(key), bool)
                        or not isinstance(payload.get(key), int)
                        or payload[key] < 1
                        for key in required_ints
                    )
                    or payload["dispatched_events"] != payload["limit"]
                    or event.causation_id != payload["last_dispatched_event_id"]
                ):
                    raise RuntimeErrorBase(
                        "EventLog runtime.reaction_halted violates event cascade boundary"
                    )
                self.events.halt_count += 1
                self.events.last_cascade = {
                    **dict(payload),
                    "root_correlation_id": event.correlation_id,
                }
                lifecycle_seen = True
            if event.event_type == "action.scheduled":
                lifecycle_seen = True
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
                pending_action_runtime[action.action_id] = (
                    self._new_action_runtime_record(
                        action, self._action_behavior(action.verb),
                    )
                )
            elif event.event_type == "action.branch_selected":
                action_id = event.payload.get("action_id")
                phase_id = event.payload.get("phase_id")
                branch_id = event.payload.get("branch_id")
                entry = pending_actions.get(action_id) if isinstance(action_id, str) else None
                behavior = self._action_behavior(entry[2].verb) if entry is not None else None
                phases = behavior.get("phases", []) if isinstance(behavior, dict) else []
                static_route = self._is_static_action_route(behavior)
                route = (
                    pending_action_runtime.get(action_id, {}).get("route")
                    if isinstance(action_id, str) else None
                )
                if static_route:
                    phase_index = next(
                        (
                            index for index, item in enumerate(phases)
                            if isinstance(item, dict) and item.get("phase_id") == phase_id
                        ),
                        None,
                    )
                else:
                    phase_index = next(
                        (
                            index for index, item in enumerate(phases[:-1])
                            if isinstance(item, dict) and item.get("phase_id") == phase_id
                        ),
                        None,
                    )
                phase = phases[phase_index] if isinstance(phase_index, int) else None
                branches = self._bounded_action_branches(
                    phase.get("branches") if isinstance(phase, dict) else None
                )
                branch = next(
                    (
                        item for item in branches or []
                        if item.get("branch_id") == branch_id
                    ),
                    None,
                )
                child = branch.get("child_action") if isinstance(branch, dict) else None
                expected_next_phase_id = (
                    branch.get("next_phase_id")
                    if static_route and isinstance(branch, dict)
                    else (
                        phases[phase_index + 1].get("phase_id")
                        if isinstance(phase_index, int) and phase_index + 1 < len(phases)
                        else None
                    )
                )
                selections = (
                    pending_action_runtime[action_id]["selected_branches"]
                    if isinstance(action_id, str) and action_id in pending_action_runtime
                    else {}
                )
                if (
                    entry is None
                    or not isinstance(phase_id, str)
                    or not isinstance(branch_id, str)
                    or branch is None
                    or phase_id in selections
                    or event.payload.get("behavior_id") != behavior.get("behavior_id")
                    or event.payload.get("actor") != entry[2].actor_id
                    or event.payload.get("verb") != entry[2].verb
                    or event.payload.get("priority") != branch["priority"]
                    or event.payload.get("next_phase_id") != expected_next_phase_id
                    or (
                        static_route
                        and (
                            not isinstance(route, dict)
                            or route.get("current_phase_id") != phase_id
                            or event.timestamp_tick != route.get("phase_due_tick")
                        )
                    )
                    or event.payload.get("child_step_id") != (
                        child.get("step_id") if isinstance(child, dict) else None
                    )
                ):
                    raise RuntimeErrorBase(
                        "EventLog action.branch_selected violates authored branch order"
                    )
                selections[phase_id] = branch_id
                lifecycle_seen = True
            elif event.event_type == "action.child_completed":
                action_id = event.payload.get("parent_action_id")
                step_id = event.payload.get("step_id")
                entry = pending_actions.get(action_id) if isinstance(action_id, str) else None
                if entry is None or not isinstance(step_id, str):
                    raise RuntimeErrorBase(
                        "EventLog action.child_completed references no pending parent"
                    )
                behavior = self._action_behavior(entry[2].verb)
                authored_steps: list[str] = []
                if isinstance(behavior, dict):
                    selections = pending_action_runtime[action_id]["selected_branches"]
                    route = pending_action_runtime[action_id].get("route")
                    phases = behavior.get("phases", [])
                    phase_by_id = {
                        phase.get("phase_id"): phase
                        for phase in phases
                        if isinstance(phase, dict)
                        and isinstance(phase.get("phase_id"), str)
                    }
                    authored_phases = (
                        [
                            phase_by_id[phase_id]
                            for phase_id in route.get("visited_phase_ids", [])
                            if phase_id in phase_by_id
                        ]
                        if self._is_static_action_route(behavior)
                        and isinstance(route, dict)
                        else phases
                    )
                    for phase in authored_phases:
                        if not isinstance(phase, dict):
                            continue
                        child_action = phase.get("child_action")
                        if isinstance(child_action, dict) and isinstance(
                            child_action.get("step_id"), str
                        ):
                            authored_steps.append(child_action["step_id"])
                        branches = self._bounded_action_branches(phase.get("branches"))
                        selected_branch_id = selections.get(phase.get("phase_id"))
                        if branches is not None and selected_branch_id is not None:
                            selected_branch = next(
                                branch for branch in branches
                                if branch["branch_id"] == selected_branch_id
                            )
                            selected_child = selected_branch.get("child_action")
                            if isinstance(selected_child, dict) and isinstance(
                                selected_child.get("step_id"), str
                            ):
                                authored_steps.append(selected_child["step_id"])
                completed_steps = pending_action_runtime[action_id]["completed_steps"]
                if (
                    len(completed_steps) >= len(authored_steps)
                    or authored_steps[len(completed_steps)] != step_id
                ):
                    raise RuntimeErrorBase(
                        "EventLog action.child_completed violates authored sequence"
                    )
                completed_steps.append(step_id)
                lifecycle_seen = True
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
                static_retry_valid = True
                if self._is_static_action_route(behavior):
                    runtime_record = pending_action_runtime[action_id]
                    route = runtime_record.get("route")
                    current_phase = next(
                        (
                            item for item in phases
                            if isinstance(item, dict)
                            and isinstance(route, dict)
                            and item.get("phase_id") == route.get("current_phase_id")
                        ),
                        None,
                    )
                    selected_branch_id = runtime_record["selected_branches"].get(
                        current_phase.get("phase_id")
                        if isinstance(current_phase, dict) else None
                    )
                    selected_branch = next(
                        (
                            item for item in self._bounded_action_branches(
                                current_phase.get("branches")
                                if isinstance(current_phase, dict) else None
                            ) or []
                            if item.get("branch_id") == selected_branch_id
                        ),
                        None,
                    )
                    expected_boundary_tick = (
                        previous_retry.get("next_retry_tick")
                        if isinstance(previous_retry, dict)
                        else route.get("phase_due_tick")
                        if isinstance(route, dict)
                        else None
                    )
                    static_retry_valid = (
                        isinstance(route, dict)
                        and selected_branch is not None
                        and selected_branch.get("next_phase_id")
                        == event.payload.get("phase_id")
                        and event.timestamp_tick == expected_boundary_tick
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
                    or not static_retry_valid
                    or not isinstance(condition_id, str)
                    or condition_id not in {
                        condition.get("condition_id")
                        for condition in phase.get("when", [])
                        if isinstance(condition, dict)
                    }
                ):
                    raise RuntimeErrorBase("EventLog action.retry_scheduled violates authored policy")
                lifecycle_seen = True
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
                action_id = event.payload.get("action_id")
                next_phase_id = event.payload.get("next_phase_id")
                if not isinstance(action_id, str) or not isinstance(next_phase_id, str):
                    raise RuntimeErrorBase("EventLog action.progressed is invalid")
                if action_id not in pending_actions:
                    raise RuntimeErrorBase(
                        "EventLog action.progressed references no pending action"
                    )
                if isinstance(action_id, str) and isinstance(next_phase_id, str):
                    entry = pending_actions.get(action_id)
                    runtime_record = pending_action_runtime.get(action_id)
                    behavior = (
                        self._action_behavior(entry[2].verb) if entry is not None else None
                    )
                    if self._is_static_action_route(behavior):
                        route = (
                            runtime_record.get("route")
                            if isinstance(runtime_record, dict) else None
                        )
                        phases = behavior.get("phases", [])
                        phase_by_id = {
                            phase.get("phase_id"): phase
                            for phase in phases
                            if isinstance(phase, dict)
                            and isinstance(phase.get("phase_id"), str)
                        }
                        phase_id = event.payload.get("phase_id")
                        phase = phase_by_id.get(phase_id)
                        next_phase = phase_by_id.get(next_phase_id)
                        selected_branch_id = (
                            runtime_record.get("selected_branches", {}).get(phase_id)
                            if isinstance(runtime_record, dict) else None
                        )
                        branch = next(
                            (
                                item for item in self._bounded_action_branches(
                                    phase.get("branches") if isinstance(phase, dict) else None
                                ) or []
                                if item.get("branch_id") == selected_branch_id
                            ),
                            None,
                        )
                        visited = (
                            route.get("visited_phase_ids")
                            if isinstance(route, dict) else None
                        )
                        elapsed = (
                            route.get("elapsed_duration_ticks")
                            if isinstance(route, dict) else None
                        )
                        next_due = (
                            event.timestamp_tick + next_phase["duration_ticks"]
                            if isinstance(next_phase, dict) else None
                        )
                        retry_ticks = {
                            retry_state.get("next_retry_tick")
                            for retry_state in runtime_record.get("retries", {}).values()
                            if isinstance(retry_state, dict)
                        } if isinstance(runtime_record, dict) else set()
                        expected_boundary_tick = (
                            next(iter(retry_ticks))
                            if retry_ticks else route.get("phase_due_tick")
                            if isinstance(route, dict) else None
                        )
                        if (
                            entry is None
                            or not isinstance(route, dict)
                            or not isinstance(phase, dict)
                            or not isinstance(next_phase, dict)
                            or branch is None
                            or branch.get("next_phase_id") != next_phase_id
                            or route.get("current_phase_id") != phase_id
                            or event.timestamp_tick != expected_boundary_tick
                            or not isinstance(visited, list)
                            or isinstance(elapsed, bool)
                            or not isinstance(elapsed, int)
                            or event.payload.get("phase_index") != len(visited)
                            or event.payload.get("completed_phases") != len(visited)
                            or event.payload.get("total_phases") != len(phases)
                            or event.payload.get("progress_ticks")
                            != elapsed + phase["duration_ticks"]
                            or event.payload.get("phase_due_tick") != next_due
                        ):
                            raise RuntimeErrorBase(
                                "EventLog action.progressed violates static route"
                            )
                        route.update({
                            "current_phase_id": next_phase_id,
                            "phase_started_tick": event.timestamp_tick,
                            "phase_due_tick": next_due,
                            "elapsed_duration_ticks": elapsed + phase["duration_ticks"],
                            "visited_phase_ids": [*visited, next_phase_id],
                        })
                        if next_phase_id == behavior.get("terminal_phase_id"):
                            routed_due = event.payload.get("due_tick")
                            if routed_due != next_due:
                                raise RuntimeErrorBase(
                                    "EventLog terminal route due_tick is invalid"
                                )
                            pending_actions[action_id] = (
                                routed_due, entry[1], entry[2],
                            )
                    pending_action_runtime.get(action_id, {}).get("retries", {}).pop(
                        next_phase_id, None
                    )
            elif event.event_type in {
                "action.completed", "action.cancelled", "action.interrupted", "action.failed",
            }:
                action_id = event.payload.get("action_id")
                if isinstance(action_id, str):
                    entry = pending_actions.get(action_id)
                    behavior = (
                        self._action_behavior(entry[2].verb) if entry is not None else None
                    )
                    if event.event_type == "action.completed" and self._is_static_action_route(
                        behavior
                    ):
                        route = pending_action_runtime.get(action_id, {}).get("route")
                        if (
                            entry is None
                            or not isinstance(route, dict)
                            or route.get("current_phase_id")
                            != behavior.get("terminal_phase_id")
                            or route.get("phase_due_tick") != event.timestamp_tick
                            or entry[0] != event.timestamp_tick
                        ):
                            raise RuntimeErrorBase(
                                "EventLog action.completed violates static terminal route"
                            )
                    lifecycle_seen = True
                    pending_actions.pop(action_id, None)
                    pending_action_runtime.pop(action_id, None)
        if lifecycle_seen:
            self.scheduler._counter = lifecycle_order
            self.scheduler._queue = list(pending_actions.values())
            heapq.heapify(self.scheduler._queue)
            self.actions = {
                action.action_id: action for _, _, action in pending_actions.values()
            }
            self.action_runtime = pending_action_runtime
        self.scheduler.tick = replay_tick

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
            "event_dispatch": self.events.diagnostics(),
            "active_player_id": self.active_player_id,
            "generated_players": sorted(self.player_profiles),
            "metrics": dict(self.metrics),
        }
