"""Read-only, state-aware narrative projections.

The Runtime Package remains the source of authored text and the StateStore
remains the source of truth for world state.  This module only projects the
two together for a particular actor; it never submits a Delta or emits an
event.  The same function is used by `look`, the terminal renderer, and the
web View Model so adapters cannot drift into different stories.
"""

from __future__ import annotations

from typing import Any

from .kernel import WorldRuntime


def render_room_description(runtime: WorldRuntime, actor_id: str, room: dict[str, Any]) -> str:
    """Return the actor-specific description for a compiled room.

    Rules are authored in ``narrative.room_overlays``.  A matching ``replace``
    rule becomes the new base description; matching ``append`` rules are then
    added in authored order.  A missing state cell never satisfies a rule,
    including a rule whose expected value is ``null``.
    """
    sections = [str(room["description"])]
    for overlay in runtime.package.get("narrative", {}).get("room_overlays", []):
        if overlay["room_id"] != room["room_id"]:
            continue
        if not conditions_match(runtime, actor_id, overlay["when"]):
            continue
        text = overlay["text"]
        if overlay.get("mode", "append") == "replace":
            sections = [text]
        else:
            sections.append(text)
    return "\n\n".join(section for section in sections if section)


def conditions_match(
    runtime: WorldRuntime,
    actor_id: str,
    conditions: list[dict[str, Any]],
    *,
    speaker_id: str | None = None,
) -> bool:
    """Match compiled StateStore conditions without granting a write path.

    ``$actor`` is available to every state-aware projection. Authored NPC
    dialogue may additionally use ``$speaker``; room overlays are rejected by
    the compiler if they try to use it, so a missing speaker fails closed.
    """
    for condition in conditions:
        owner_ref = condition["owner"]
        if owner_ref == "$actor":
            owner = actor_id
        elif owner_ref == "$speaker":
            if speaker_id is None:
                return False
            owner = speaker_id
        else:
            owner = owner_ref
        namespace = condition["namespace"]
        key = condition["key"]
        if runtime.state.version(owner, namespace, key) < 0:
            return False
        if runtime.state.get(owner, namespace, key) != condition["equals"]:
            return False
    return True
