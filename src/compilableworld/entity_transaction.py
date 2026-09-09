from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict

from .kernel import KernelTransactionError, RuntimeErrorBase, WorldRuntime
from .models import ActionIR, ActionReceipt, ActionStatus, EntityDelta, EventIR, TransitionResult


ENTITY_TRANSACTION_CAPABILITY = "entity_transaction/v0.1"


class EntityTransactionRuntime(WorldRuntime):
    """Additive WorldRuntime extension for atomic entity creation.

    StateDelta, create-only EntityDelta and EventIR are committed under the
    same local rollback boundary. Modules must explicitly declare
    ``entity_transaction/v0.1`` in ``requires_kernel`` before returning an
    EntityDelta. The base WorldRuntime remains unchanged for existing hosts.
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
            if not delta.expected_absent:
                raise RuntimeErrorBase("create EntityDelta must require expected_absent=true in v0.1")
            entity_id = delta.entity.entity_id
            if not entity_id:
                raise RuntimeErrorBase("create EntityDelta requires a non-empty entity_id")
            if entity_id in seen:
                raise RuntimeErrorBase(f"duplicate entity create in one transaction: {entity_id}")
            if self.registry.contains(entity_id):
                raise RuntimeErrorBase(f"entity create precondition failed; already exists: {entity_id}")
            seen.add(entity_id)

    def _apply_entity_deltas(self, entity_deltas: list[EntityDelta]) -> list[dict]:
        applied: list[dict] = []
        for delta in entity_deltas:
            entity = deepcopy(delta.entity)
            self.registry.add(entity)
            self.dynamic_entities.add(entity.entity_id)
            applied.append({
                "operation": "create",
                "entity": asdict(entity),
            })
        return applied

    def _execute(self, action: ActionIR) -> ActionReceipt:
        scheduled_behavior = self._action_behavior(action.verb) if action.status == ActionStatus.SCHEDULED else None
        started_event = (
            self._action_lifecycle_event("action.started", action, scheduled_behavior)
            if scheduled_behavior else None
        )
        state_before = deepcopy(self.state.export())
        entities_before = deepcopy(self.registry._entities)
        dynamic_before = set(self.dynamic_entities)
        try:
            module = self.module_for(action.verb)
            action.status = ActionStatus.VALIDATED
            action.status = ActionStatus.EXECUTING
            result = module.evaluate(action, self)
            if not result.accepted:
                return self._fail(action, result.message, lifecycle_started=scheduled_behavior is not None)

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
                if scheduled_behavior else None
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
            return self._fail(action, str(exc), lifecycle_started=scheduled_behavior is not None)

        action.status = ActionStatus.COMPLETED
        self.action_runtime.pop(action.action_id, None)
        self.metrics["actions_completed"] += 1
        for event in emitted:
            self.events.publish(event)
            self.metrics[f"event:{event.event_type}"] += 1
        return ActionReceipt(
            action.action_id,
            action.status,
            result.message,
            [event.event_id for event in emitted],
            [item["path"] for item in applied],
            [item["entity"]["entity_id"] for item in applied_entities],
        )
