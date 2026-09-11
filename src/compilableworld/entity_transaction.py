from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import fnmatch
import json
import re
from typing import Any, Iterable

from .kernel import KernelTransactionError, RuntimeErrorBase, WorldRuntime
from .models import ActionIR, ActionReceipt, ActionStatus, Entity, EntityDelta, EventIR, TransitionResult


ENTITY_TRANSACTION_CAPABILITY = "entity_transaction/v0.1"


def _validated_entity(raw: Any, *, allow_legacy_defaults: bool = False) -> Entity:
    """One JSON-preserving shape for create, Snapshot and EventLog restore."""
    if allow_legacy_defaults and isinstance(raw, dict):
        raw = {"components": [], "metadata": {}, **raw}
    if (
        not isinstance(raw, dict)
        or set(raw) != {"entity_id", "entity_type", "name", "components", "metadata"}
        or not isinstance(raw.get("entity_id"), str)
        or re.fullmatch(r"[a-z][a-z0-9_.-]*", raw["entity_id"]) is None
        or any(not isinstance(raw.get(key), str) or not raw[key] for key in ("entity_type", "name"))
        or not isinstance(raw.get("components"), list)
        or any(not isinstance(part, str) or not part for part in raw["components"])
        or not isinstance(raw.get("metadata"), dict)
    ):
        raise RuntimeErrorBase("Entity transaction entity shape is invalid")
    try:
        # JSON must not change tuples, keys, NaN, etc. across a save/restart.
        encoded = json.dumps(raw, ensure_ascii=False, allow_nan=False)
        detached = json.loads(encoded)
        if detached != raw:
            raise ValueError("entity must be JSON-preserving")
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise RuntimeErrorBase("Entity transaction entity must contain JSON data") from exc
    return Entity(**detached)


class EntityTransactionRuntime(WorldRuntime):
    """Additive WorldRuntime extension for atomic entity creation.

    StateDelta, create-only EntityDelta and EventIR are committed under the
    same local rollback boundary. Modules must explicitly declare
    ``entity_transaction/v0.1`` in ``requires_kernel`` before returning an
    EntityDelta. Snapshot v0.6 remains compatible; Replay requires the emitting
    module's registered contract but never re-executes its evaluate method.
    """

    def _restore_entity_transaction(
        self,
        state_before: dict,
        entities_before: dict,
        dynamic_before: set[str],
    ) -> None:
        self.state.import_state(state_before)
        self.registry._entities = deepcopy(entities_before)
        self.dynamic_entities = set(dynamic_before)

    def _validate_entity_deltas(self, result: TransitionResult, module) -> None:
        if not result.entity_deltas:
            return
        if ENTITY_TRANSACTION_CAPABILITY not in module.contract.requires_kernel:
            raise RuntimeErrorBase(
                f"module {module.contract.module_id} emitted EntityDelta without "
                f"declaring {ENTITY_TRANSACTION_CAPABILITY}"
            )
        seen: set[str] = set()
        for delta in result.entity_deltas:
            if not isinstance(delta, EntityDelta):
                raise RuntimeErrorBase("entity_deltas must contain EntityDelta values")
            if delta.operation != "create":
                raise RuntimeErrorBase(
                    f"unsupported EntityDelta operation in {ENTITY_TRANSACTION_CAPABILITY}: {delta.operation}"
                )
            if delta.expected_absent is not True:
                raise RuntimeErrorBase("create EntityDelta must require expected_absent=true in v0.1")
            if not isinstance(delta.entity, Entity):
                raise RuntimeErrorBase("EntityDelta must contain an Entity")
            _validated_entity(asdict(delta.entity))
            if delta.source_module != "" and delta.source_module != module.contract.module_id:
                raise RuntimeErrorBase("EntityDelta source_module does not match its creator")
            entity_id = delta.entity.entity_id
            if not entity_id:
                raise RuntimeErrorBase("create EntityDelta requires a non-empty entity_id")
            if entity_id in seen:
                raise RuntimeErrorBase(f"duplicate entity create in one transaction: {entity_id}")
            if self.registry.contains(entity_id):
                raise RuntimeErrorBase(f"entity create precondition failed; already exists: {entity_id}")
            if any(raw["entity_id"] == entity_id for raw in self.package["entities"]):
                raise RuntimeErrorBase("EntityDelta cannot reuse a reserved Package entity ID")
            seen.add(entity_id)

    def _apply_entity_deltas(self, entity_deltas: list[EntityDelta]) -> list[dict]:
        applied: list[dict] = []
        for delta in entity_deltas:
            entity = _validated_entity(asdict(delta.entity))
            self.registry.add(entity)
            self.dynamic_entities.add(entity.entity_id)
            applied.append({
                "operation": "create",
                "entity": asdict(entity),
            })
        return applied

    def _restore_snapshot_payload(self, payload: Any, *, record_event: bool) -> None:
        if isinstance(payload, dict) and isinstance(payload.get("dynamic_entities", []), list):
            for raw in payload.get("dynamic_entities", []):
                _validated_entity(raw, allow_legacy_defaults=True)
        super()._restore_snapshot_payload(payload, record_event=record_event)

    def _validate_replay_support(self, events: list[EventIR]) -> None:
        seen_ids: set[str] = set()
        for event in events:
            if (
                not isinstance(event, EventIR)
                or not isinstance(event.event_id, str) or not event.event_id
                or event.event_id in seen_ids
                or not isinstance(event.payload, dict)
            ):
                raise RuntimeErrorBase("Entity Replay requires unique, well-formed EventIR records")
            seen_ids.add(event.event_id)
            if event.event_type == "entity.committed":
                module = self.modules.get(event.source)
                if module is None or ENTITY_TRANSACTION_CAPABILITY not in module.contract.requires_kernel:
                    raise RuntimeErrorBase("Entity Replay requires the registered creator capability")

    def _apply_replayed_entity_commit(self, event: EventIR, previous: EventIR | None) -> None:
        if (
            type(event.version) is not int or event.version != 1
            or event.authority != "runtime" or event.visibility != "audit"
            or not isinstance(event.target, str) or not self.registry.contains(event.target)
            or not isinstance(event.causation_id, str) or not event.causation_id
            or not isinstance(event.correlation_id, str) or not event.correlation_id
            or previous is None or previous.event_type != "state.committed"
            or type(previous.version) is not int or previous.version != 1
            or previous.authority != "runtime" or previous.visibility != "audit"
            or any(getattr(previous, key) != getattr(event, key) for key in (
                "source", "target", "causation_id", "correlation_id", "timestamp_tick",
            ))
            or set(event.payload) != {"applied"}
            or not isinstance(event.payload["applied"], list) or not event.payload["applied"]
        ):
            raise RuntimeErrorBase("EventLog entity.committed transaction envelope is invalid")

        creator = self.modules[event.source]
        applied_state = previous.payload.get("applied")
        if not isinstance(applied_state, list):
            raise RuntimeErrorBase("Entity Replay paired StateDelta payload is invalid")
        for cell in applied_state:
            if (
                not isinstance(cell, dict)
                or set(cell) != {"path", "owner", "namespace", "key", "value", "version"}
                or any(not isinstance(cell.get(key), str) or not cell[key]
                       for key in ("owner", "namespace", "key"))
                or cell["path"] != self.state.path(cell["owner"], cell["namespace"], cell["key"])
                or type(cell["version"]) is not int or cell["version"] < 0
                or not any(fnmatch.fnmatch(f"{cell['namespace']}.{cell['key']}", pattern)
                           for pattern in creator.contract.write)
            ):
                raise RuntimeErrorBase("Entity Replay paired StateDelta violates its creator contract")

        additions: list[Entity] = []
        seen: set[str] = set()
        for row in event.payload["applied"]:
            if not isinstance(row, dict) or set(row) != {"operation", "entity"} or row["operation"] != "create":
                raise RuntimeErrorBase("Entity Replay supports create-only records")
            entity = _validated_entity(row["entity"])
            if entity.entity_id in seen or self.registry.contains(entity.entity_id):
                raise RuntimeErrorBase("Entity Replay create requires an absent entity ID")
            if any(raw["entity_id"] == entity.entity_id for raw in self.package["entities"]):
                raise RuntimeErrorBase("Entity Replay cannot reuse a reserved Package entity ID")
            seen.add(entity.entity_id)
            additions.append(entity)
        for entity in additions:
            self.registry.add(entity)
            self.dynamic_entities.add(entity.entity_id)

    def replay(self, events: Iterable[EventIR]) -> None:
        """Restore the whole stream atomically in memory, without logging or publishing it."""
        before = deepcopy({
            "cells": self.state._cells,
            "entities": self.registry._entities,
            "dynamic": self.dynamic_entities,
            "profiles": self.player_profiles,
            "active_player": self.active_player_id,
            "tick": self.scheduler.tick,
            "counter": self.scheduler._counter,
            "queue": self.scheduler._queue,
            "actions": self.actions,
            "action_runtime": self.action_runtime,
            "halt_count": self.events.halt_count,
            "last_cascade": self.events.last_cascade,
        })
        try:
            super().replay(deepcopy(list(events)))
        except Exception as exc:
            self.state._cells = before["cells"]
            self.registry._entities = before["entities"]
            self.dynamic_entities = before["dynamic"]
            self.player_profiles = before["profiles"]
            self.active_player_id = before["active_player"]
            self.scheduler.tick = before["tick"]
            self.scheduler._counter = before["counter"]
            self.scheduler._queue = before["queue"]
            self.actions = before["actions"]
            self.action_runtime = before["action_runtime"]
            self.events.halt_count = before["halt_count"]
            self.events.last_cascade = before["last_cascade"]
            if isinstance(exc, RuntimeErrorBase):
                raise
            if isinstance(exc, (KeyError, TypeError, ValueError, AttributeError, OverflowError, RecursionError)):
                raise RuntimeErrorBase("Entity Replay contains an invalid record") from exc
            raise

    def _execute(self, action: ActionIR) -> ActionReceipt:
        was_scheduled = action.status == ActionStatus.SCHEDULED
        scheduled_behavior = self._action_behavior(action.verb) if was_scheduled else None
        started_event = (
            self._action_lifecycle_event("action.started", action, scheduled_behavior)
            if was_scheduled else None
        )
        state_before = deepcopy(self.state.export())
        entities_before = deepcopy(self.registry._entities)
        dynamic_before = set(self.dynamic_entities)
        try:
            module = self.module_for(action.verb)
            if not self.registry.contains(action.actor_id):
                return self._fail(
                    action, f"未知 actor: {action.actor_id}", lifecycle_started=was_scheduled,
                )
            action.status = ActionStatus.VALIDATED
            action.status = ActionStatus.EXECUTING
            result = module.evaluate(action, self)
            if not result.accepted:
                return self._fail(action, result.message, lifecycle_started=was_scheduled)

            self._validate_entity_deltas(result, module)
            applied = self.state.commit(result.deltas, module.contract.write)
            applied_entities = self._apply_entity_deltas(result.entity_deltas)

            commit_event = EventIR(
                event_type="state.committed",
                source=module.contract.module_id,
                target=action.actor_id,
                causation_id=action.action_id,
                correlation_id=action.correlation_id,
                timestamp_tick=self.scheduler.tick,
                visibility="audit",
                payload={"applied": applied},
            )
            entity_commit_event = (
                EventIR(
                    event_type="entity.committed",
                    source=module.contract.module_id,
                    target=action.actor_id,
                    causation_id=action.action_id,
                    correlation_id=action.correlation_id,
                    timestamp_tick=self.scheduler.tick,
                    visibility="audit",
                    payload={"applied": applied_entities},
                )
                if applied_entities
                else None
            )
            completed_event = (
                self._action_lifecycle_event("action.completed", action, scheduled_behavior)
                if was_scheduled else None
            )
            emitted = [
                *([started_event] if started_event else []),
                commit_event,
                *([entity_commit_event] if entity_commit_event else []),
                *result.events,
                *([completed_event] if completed_event else []),
            ]
            for event in emitted:
                event.causation_id = event.causation_id or action.action_id
                event.correlation_id = event.correlation_id or action.correlation_id
                event.timestamp_tick = self.scheduler.tick
            self.event_log.append_batch(emitted)
        except KernelTransactionError:
            self._restore_entity_transaction(state_before, entities_before, dynamic_before)
            action.status = ActionStatus.FAILED
            self.action_runtime.pop(action.action_id, None)
            self.metrics["actions_failed"] += 1
            raise
        except RuntimeErrorBase as exc:
            self._restore_entity_transaction(state_before, entities_before, dynamic_before)
            return self._fail(action, str(exc), lifecycle_started=was_scheduled)

        action.status = ActionStatus.COMPLETED
        self.action_runtime.pop(action.action_id, None)
        self.metrics["actions_completed"] += 1
        self._publish_committed_events(emitted)
        return ActionReceipt(
            action.action_id,
            action.status,
            result.message,
            [event.event_id for event in emitted],
            [item["path"] for item in applied],
            [item["entity"]["entity_id"] for item in applied_entities],
        )
