from __future__ import annotations

from copy import deepcopy
from typing import Any

from compilableworld.kernel import WorldRuntime
from compilableworld.models import EventIR
from compilableworld.webgateway import build_view_model

from .contracts import (
    EVENT_PAGE_CONTRACT,
    SCENE_CONTRACT,
    SESSION_CONTRACT,
    WORLD_STATUS_CONTRACT,
    WorldSession,
)
from .policy import event_visible_to


def session_projection(session: WorldSession) -> dict[str, Any]:
    return {
        "format": SESSION_CONTRACT,
        "read_only": True,
        "session": session.to_dict(),
        "world_state_changed": False,
    }


def world_status_projection(runtime: WorldRuntime, session: WorldSession) -> dict[str, Any]:
    manifest = runtime.package["manifest"]
    actor = runtime.registry.get(session.actor_id)
    room_id = runtime.state.get(session.actor_id, "position", "room")
    return {
        "format": WORLD_STATUS_CONTRACT,
        "read_only": True,
        "world_state_changed": False,
        "session_id": session.session_id,
        "world": {
            "world_id": manifest["world_id"],
            "world_version": manifest["world_version"],
            "runtime_version": manifest["runtime_version"],
            "package_format": runtime.package.get("format"),
            "runtime_instance_id": session.runtime_instance_id,
            "tick": runtime.scheduler.tick,
            "event_count": len(runtime.event_log.events),
            "queued_actions": runtime.scheduler.queued,
            "modules": {
                module_id: module.contract.version
                for module_id, module in sorted(runtime.modules.items())
            },
            "schema_contracts": dict(runtime.package.get("schema_contracts", {})),
        },
        "actor": {
            "actor_id": session.actor_id,
            "name": actor.name,
            "entity_type": actor.entity_type,
            "room_id": room_id,
            "alive": runtime.state.get(session.actor_id, "status", "alive", True),
        },
    }


def scene_projection(runtime: WorldRuntime, session: WorldSession) -> dict[str, Any]:
    return {
        "format": SCENE_CONTRACT,
        "read_only": True,
        "world_state_changed": False,
        "session_id": session.session_id,
        "event_cursor": len(runtime.event_log.events),
        # Keep the transport-neutral service read-only even for in-process
        # callers. build_view_model includes nested actor metadata that can be
        # shared with the Runtime registry.
        "view": deepcopy(build_view_model(runtime, session.actor_id)),
    }


def event_projection(event: EventIR) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "source": event.source,
        "target": event.target,
        "timestamp_tick": event.timestamp_tick,
        "visibility": event.visibility,
        "authority": event.authority,
        "version": event.version,
        "causation_id": event.causation_id,
        "correlation_id": event.correlation_id,
        # Event payloads may contain nested mutable dictionaries/lists. Never
        # expose the EventLog's live payload through a read projection.
        "payload": deepcopy(event.payload),
    }


def recent_events_projection(
    runtime: WorldRuntime,
    session: WorldSession,
    *,
    after_index: int = 0,
    limit: int = 20,
) -> dict[str, Any]:
    if isinstance(after_index, bool) or not isinstance(after_index, int) or after_index < 0:
        raise ValueError("after_index must be a non-negative integer")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")

    raw_events = runtime.event_log.events
    cursor = min(after_index, len(raw_events))
    visible: list[dict[str, Any]] = []
    while cursor < len(raw_events) and len(visible) < limit:
        event = raw_events[cursor]
        cursor += 1
        if event_visible_to(event, session):
            visible.append(event_projection(event))

    return {
        "format": EVENT_PAGE_CONTRACT,
        "read_only": True,
        "world_state_changed": False,
        "session_id": session.session_id,
        "after_index": after_index,
        "next_index": cursor,
        "total_raw_events": len(raw_events),
        "has_more": cursor < len(raw_events),
        "events": visible,
    }
