"""Deterministic ScenarioIR runner.

Scenarios are test-only projections: ``given`` seeds an in-memory Runtime,
``when`` submits normal ActionIR through the Kernel, and ``expect`` checks
StateStore/EventIR results.  A scenario cannot write the Authoring Layer or
change the compiled package on disk.
"""

from __future__ import annotations

from typing import Any

from .kernel import WorldRuntime
from .models import ActionIR
from .modules import install_builtin_modules


class ScenarioRunError(ValueError):
    pass


def _resolve_ref(value: str | None, actor_id: str) -> str | None:
    if value == "$actor":
        return actor_id
    return value


def _scenario(package: dict[str, Any], scenario_id: str) -> dict[str, Any]:
    source = package.get("scenarios", {})
    entries = source.get("scenarios", []) if isinstance(source, dict) else []
    for entry in entries:
        if isinstance(entry, dict) and entry.get("scenario_id") == scenario_id:
            return entry
    raise ScenarioRunError(f"找不到 ScenarioIR: {scenario_id}")


def run_scenario(
    package: dict[str, Any],
    scenario_id: str,
    *,
    actor_id: str | None = None,
) -> dict[str, Any]:
    """Run one compiled ScenarioIR and return a machine-readable report."""
    scenario = _scenario(package, scenario_id)
    runtime = WorldRuntime(package)
    install_builtin_modules(runtime)

    chosen_actor = actor_id or scenario.get("actor_id") or package.get("world", {}).get("default_player_entity")
    if not isinstance(chosen_actor, str) or not runtime.registry.contains(chosen_actor):
        raise ScenarioRunError(f"Scenario actor 不存在: {chosen_actor}")

    for assertion in scenario.get("given", []):
        owner = _resolve_ref(assertion["owner"], chosen_actor)
        runtime.state.seed(owner, assertion["namespace"], assertion["key"], assertion["equals"])

    start_event_count = len(runtime.event_log.events)
    action_results: list[dict[str, Any]] = []
    expected_status = scenario.get("expect", {}).get("status", "completed")
    for action_index, raw_action in enumerate(scenario.get("when", [])):
        action_actor = _resolve_ref(raw_action.get("actor", "$actor"), chosen_actor)
        if not action_actor:
            raise ScenarioRunError(f"Scenario action[{action_index}] 缺少 actor")
        action = ActionIR(
            actor_id=action_actor,
            verb=raw_action["verb"],
            target_id=raw_action.get("target_id"),
            args=dict(raw_action.get("args", {})),
            authority="scenario",
        )
        receipt = runtime.submit(action, delay=int(raw_action.get("delay", 0)))
        receipts = [receipt]
        if receipt.status.value == "scheduled":
            receipts = runtime.advance(int(raw_action.get("delay", 0)))
        final_receipt = receipts[-1] if receipts else receipt
        action_results.append({
            "index": action_index,
            "verb": action.verb,
            "status": final_receipt.status.value,
            "message": final_receipt.message,
            "event_ids": list(final_receipt.event_ids),
        })

    observed_events = runtime.event_log.events[start_event_count:]
    observed_event_types = [event.event_type for event in observed_events]
    assertions: list[dict[str, Any]] = []
    for expected in scenario.get("expect", {}).get("state", []):
        owner = _resolve_ref(expected["owner"], chosen_actor)
        actual = runtime.state.get(owner, expected["namespace"], expected["key"])
        assertions.append({
            "kind": "state",
            "owner": owner,
            "namespace": expected["namespace"],
            "key": expected["key"],
            "expected": expected["equals"],
            "actual": actual,
            "passed": actual == expected["equals"],
        })

    expected_events = list(scenario.get("expect", {}).get("events", []))
    for event_type in expected_events:
        assertions.append({
            "kind": "event",
            "expected": event_type,
            "actual": event_type if event_type in observed_event_types else None,
            "passed": event_type in observed_event_types,
        })

    status_passed = all(result["status"] == expected_status for result in action_results)
    assertions.append({
        "kind": "action_status",
        "expected": expected_status,
        "actual": [result["status"] for result in action_results],
        "passed": status_passed,
    })
    passed = all(assertion["passed"] for assertion in assertions)
    return {
        "scenario_id": scenario_id,
        "title": scenario.get("title", ""),
        "actor_id": chosen_actor,
        "passed": passed,
        "action_results": action_results,
        "observed_event_types": observed_event_types,
        "assertions": assertions,
        "diagnostics": runtime.diagnostics(),
    }


__all__ = ["ScenarioRunError", "run_scenario"]
