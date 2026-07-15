from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from compilableworld.compiler import compile_world
from compilableworld.models import EventIR
from compilableworld.player_generation import generate_character
from compilableworld_mcp import MCPWorldError, ReadOnlyWorldService

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "gray_crown"


class ReadOnlyMCPTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        package_path = compile_world(EXAMPLE, Path(self.temp.name) / "build")
        self.service = ReadOnlyWorldService()
        self.world_id = self.service.register_package(package_path, runtime_instance_id="runtime_test")
        self.runtime = self.service.runtime_for_testing(self.world_id)
        self.default_actor = self.runtime.package["world"]["default_player_entity"]

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _snapshot(self) -> str:
        payload = {
            "state": self.runtime.state.export(),
            "events": [event.to_dict() for event in self.runtime.event_log.events],
            "tick": self.runtime.scheduler.tick,
            "actions": sorted(self.runtime.actions),
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    def _session_id(self, **kwargs: object) -> str:
        opened = self.service.open_world_session(self.world_id, **kwargs)
        return opened["session"]["session_id"]

    def test_read_only_tools_are_json_serializable_and_do_not_mutate_world(self) -> None:
        before = self._snapshot()
        session_id = self._session_id(client_id="unit-test", model_id="none")
        worlds = self.service.list_worlds()
        status = self.service.get_world_status(session_id)
        scene = self.service.get_current_scene(session_id)
        events = self.service.get_recent_events(session_id)
        closed = self.service.close_world_session(session_id)
        after = self._snapshot()

        self.assertEqual(before, after)
        self.assertEqual(status["format"], "compilableworld.mcp-world-status/v0.1")
        self.assertEqual(scene["format"], "compilableworld.mcp-scene/v0.1")
        self.assertEqual(scene["view"]["actor"], self.default_actor)
        self.assertEqual(events["events"], [])
        self.assertTrue(closed["closed"])
        self.assertEqual(worlds["worlds"][0]["world_id"], self.world_id)
        json.dumps([worlds, status, scene, events, closed], ensure_ascii=False)

    def test_unknown_world_actor_and_session_fail_closed(self) -> None:
        with self.assertRaisesRegex(MCPWorldError, "unknown world") as world_error:
            self.service.open_world_session("missing")
        self.assertEqual(world_error.exception.code, "WORLD_NOT_FOUND")

        with self.assertRaisesRegex(MCPWorldError, "unknown actor") as actor_error:
            self.service.open_world_session(self.world_id, actor_id="missing")
        self.assertEqual(actor_error.exception.code, "ACTOR_NOT_FOUND")

        with self.assertRaises(MCPWorldError) as session_error:
            self.service.get_world_status("missing")
        self.assertEqual(session_error.exception.code, "SESSION_INVALID")

    def test_event_visibility_and_cursor_preserve_runtime_order(self) -> None:
        actor = self.default_actor
        self.runtime.event_log.append(EventIR("world.public", "test", {"n": 1}, visibility="public"))
        self.runtime.event_log.append(EventIR("world.private", "test", {"n": 2}, target=actor, visibility="private"))
        self.runtime.event_log.append(EventIR("world.other", "test", {"n": 3}, target="npc.guard", visibility="private"))
        self.runtime.event_log.append(EventIR("world.audit", "test", {"n": 4}, visibility="audit"))
        self.runtime.event_log.append(EventIR("world.public2", "test", {"n": 5}, visibility="public"))

        player_session = self._session_id(actor_id=actor, role="player")
        page = self.service.get_recent_events(player_session, after_index=0, limit=2)
        self.assertEqual([event["event_type"] for event in page["events"]], ["world.public", "world.private"])
        self.assertEqual(page["next_index"], 2)
        next_page = self.service.get_recent_events(player_session, after_index=page["next_index"], limit=10)
        self.assertEqual([event["event_type"] for event in next_page["events"]], ["world.public2"])
        self.assertEqual(next_page["next_index"], 5)

        reviewer_session = self._session_id(actor_id=actor, role="reviewer")
        reviewer_page = self.service.get_recent_events(reviewer_session, limit=10)
        self.assertEqual(
            [event["event_type"] for event in reviewer_page["events"]],
            ["world.public", "world.private", "world.other", "world.audit", "world.public2"],
        )

    def test_projection_results_are_detached_from_runtime_state(self) -> None:
        self.runtime.event_log.append(
            EventIR("world.public", "test", {"nested": {"value": 1}}, visibility="public")
        )
        event_session = self._session_id(actor_id=self.default_actor)
        page = self.service.get_recent_events(event_session)
        page["events"][0]["payload"]["nested"]["value"] = 999
        self.assertEqual(self.runtime.event_log.events[0].payload["nested"]["value"], 1)

        generated_actor = self.runtime.create_player(generate_character(seed=77, name="Detached"))
        scene_session = self._session_id(actor_id=generated_actor)
        scene = self.service.get_current_scene(scene_session)
        scene["view"]["character"]["generation"]["attributes"]["str"] = 999
        self.assertNotEqual(
            self.runtime.registry.get(generated_actor).metadata["generation"]["attributes"]["str"],
            999,
        )

    def test_invalid_event_pagination_is_a_stable_argument_error(self) -> None:
        session_id = self._session_id()
        with self.assertRaises(MCPWorldError) as limit_error:
            self.service.get_recent_events(session_id, limit=0)
        self.assertEqual(limit_error.exception.code, "INVALID_ARGUMENT")
        self.assertFalse(limit_error.exception.retryable)

    def test_duplicate_world_registration_is_rejected(self) -> None:
        with self.assertRaises(MCPWorldError) as duplicate:
            self.service.register_runtime(self.runtime)
        self.assertEqual(duplicate.exception.code, "STATE_CONFLICT")

    def test_open_and_close_session_do_not_change_runtime_active_player(self) -> None:
        self.assertIsNone(self.runtime.active_player_id)
        session_id = self._session_id()
        self.assertIsNone(self.runtime.active_player_id)
        self.service.close_world_session(session_id)
        self.assertIsNone(self.runtime.active_player_id)


class MCPContractArtifactTests(unittest.TestCase):
    def test_server_module_import_does_not_require_optional_sdk(self) -> None:
        from compilableworld_mcp import server

        self.assertTrue(callable(server.build_mcp_server))

    def test_readonly_schema_is_versioned(self) -> None:
        schema = json.loads((ROOT / "schemas" / "mcp-readonly.v0.1.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["$id"], "compilableworld.schema/mcp-readonly/v0.1")
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")


if __name__ == "__main__":
    unittest.main()
