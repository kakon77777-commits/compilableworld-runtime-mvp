"""Deterministic, state-aware NPC dialogue selection.

Dialogue is an authored projection, not a second state machine: the compiled
package supplies candidate lines, the Runtime supplies read-only state, and
``DialogueModule`` emits the selected line as EventIR. No dialogue line has a
direct StateStore write path; quest changes remain owned by QuestModule's
event-reaction rules.
"""

from __future__ import annotations

from typing import Any

from .kernel import WorldRuntime
from .narrative import conditions_match


def select_dialogue(
    runtime: WorldRuntime,
    actor_id: str,
    speaker_id: str,
    requested_topic: str,
) -> dict[str, Any] | None:
    """Pick one compiled line, deterministically.

    First try the requested topic. If no line's conditions are satisfied,
    fall back to that speaker's ``default`` topic. Within a topic, a line
    with more satisfied conditions wins; ties retain source order. This makes
    an explicit state-specific line override an unconditional fallback without
    making authoring order a hidden priority language.
    """
    entries = runtime.package.get("dialogues", {}).get("dialogues", [])
    exact = _matching(entries, runtime, actor_id, speaker_id, requested_topic)
    if exact:
        return exact
    if requested_topic != "default":
        return _matching(entries, runtime, actor_id, speaker_id, "default")
    return None


def _matching(
    entries: list[dict[str, Any]],
    runtime: WorldRuntime,
    actor_id: str,
    speaker_id: str,
    topic: str,
) -> dict[str, Any] | None:
    matches = [
        entry for entry in entries
        if entry["speaker_id"] == speaker_id
        and entry["topic"] == topic
        and conditions_match(runtime, actor_id, entry["when"], speaker_id=speaker_id)
    ]
    if not matches:
        return None
    return max(matches, key=lambda entry: len(entry["when"]))
