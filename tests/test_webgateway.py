from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from compilableworld.compiler import compile_world
from compilableworld.kernel import WorldRuntime
from compilableworld.modules import install_builtin_modules
from compilableworld.webgateway import _Handler


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "mingyun_zhiyu_peace_city"


class WebGatewayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        package = compile_world(EXAMPLE, self.temp.name)
        self.runtime = WorldRuntime.from_package(package)
        install_builtin_modules(self.runtime)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.server.runtime = self.runtime  # type: ignore[attr-defined]
        self.server.actor_id = "player.newcomer"  # type: ignore[attr-defined]
        self.server.lock = threading.Lock()  # type: ignore[attr-defined]
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def _get(self, path: str) -> dict:
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=5) as resp:
            return json.loads(resp.read())

    def _post(self, path: str, body: dict) -> dict:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())

    def test_index_page_serves_html(self) -> None:
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/", timeout=5) as resp:
            body = resp.read().decode("utf-8")
        self.assertEqual(resp.status, 200)
        self.assertIn("<title>CompilableWorld Runtime</title>", body)

    def test_state_endpoint_reflects_current_room(self) -> None:
        view = self._get("/api/state")
        self.assertEqual(view["room"]["id"], "room.registration_office")
        self.assertEqual(view["health"]["current"], 80)  # CON=10 floor attribute -> HP=CON*8
        self.assertEqual(view["wallet"]["currency"], 0)
        quest = next(q for q in view["quests"] if q["id"] == "quest.find_work")
        self.assertEqual(quest["state"], "unstarted")

    def test_character_templates_endpoint_lists_ai_suggestions(self) -> None:
        result = self._get("/api/character/templates")
        self.assertIn("balanced", [item["template_id"] for item in result["templates"]])
        self.assertTrue(all(item["canon_status"] == "suggestion" for item in result["templates"]))

    def test_studio_overview_endpoint_is_read_only_runtime_projection(self) -> None:
        self.runtime.package["studio"] = {
            "semantic_records_are_metadata_only": True,
            "semantic_records_format": "compilableworld.studio-semantic-records/v0.1",
            "semantic_records": {"quest.web": {"instructions": [{"id": "instruction.web"}]}},
        }
        result = self._get("/api/studio/overview")
        self.assertEqual(result["format"], "compilableworld.studio-overview/v0.1")
        self.assertEqual(result["planes"]["fms"]["world_id"], "mingyun_zhiyu_peace_city_slice")
        self.assertIn("quest.core", result["planes"]["tms"]["declared_modules"])
        self.assertIn("runtime", result)
        self.assertEqual(
            result["semantic_records"]["state_machines"]["quest.web"]["instructions"][0]["id"],
            "instruction.web",
        )

    def test_studio_function_catalog_and_preview_endpoint(self) -> None:
        catalog = self._get("/api/studio/functions")
        self.assertEqual(catalog["format"], "compilableworld.function-catalog/v0.1")
        self.assertIn("combat.damage", [item["function_id"] for item in catalog["functions"]])

        preview = self._post(
            "/api/studio/function-preview",
            {"function_id": "combat.damage", "inputs": {"ar_effective": 1134.9, "dr": 606.8}},
        )
        self.assertEqual(preview["format"], "compilableworld.function-preview/v0.1")
        self.assertTrue(preview["read_only"])
        self.assertEqual(preview["result"], 83)

    def test_studio_schema_catalog_endpoint_is_read_only(self) -> None:
        result = self._get("/api/studio/schemas")
        self.assertEqual(result["format"], "compilableworld.schema-catalog/v0.1")
        self.assertTrue(result["read_only"])
        self.assertEqual(
            {record["key"] for record in result["schemas"]},
            {
                "functions", "scenarios", "runtime_package", "rooms", "exits",
                "entities", "items", "state_machines", "studio_world_ir", "studio_mapping",
            },
        )

    def test_studio_import_endpoint_is_read_only_and_preserves_semantics(self) -> None:
        before = self._get("/api/state")
        result = self._post(
            "/api/studio/import",
            {
                "source_path": "generated-draft.yaml",
                "source_text": """
                kind: state_machine
                id: quest.generated
                initial: dormant
                states: [dormant, active]
                variables:
                  - id: trust
                    random:
                      kind: integer
                      min: 0
                      max: 5
                events:
                  - id: dialogue.responded
                instructions:
                  - id: ask
                    examples: ["Can I help?"]
                responses:
                  - id: greeting
                    text: "The clerk nods."
                transitions:
                  - from: dormant
                    to: active
                    on: dialogue.responded
                """,
            },
        )
        after = self._get("/api/state")
        machine = result["world_ir"]["state_machines"][0]
        self.assertEqual(result["format"], "compilableworld.studio-import-result/v0.1")
        self.assertTrue(result["read_only"])
        self.assertEqual(result["mapping_suggestion"]["format"], "compilableworld.studio-mapping/v0.1")
        self.assertEqual(machine["variables"][0]["random"]["max"], 5)
        self.assertEqual(machine["instructions"][0]["examples"], ["Can I help?"])
        self.assertEqual(before["tick"], after["tick"])
        self.assertEqual(before["room"], after["room"])

        validation = self._post(
            "/api/studio/validate-mapping",
            {"world_ir": result["world_ir"], "mapping": result["mapping_suggestion"]},
        )
        self.assertEqual(validation["format"], "compilableworld.studio-mapping-validation-result/v0.1")
        self.assertTrue(validation["read_only"])
        self.assertTrue(validation["report"]["mapping_complete"])
        self.assertTrue(validation["report"]["runtime_ready"])

    def test_studio_preview_allows_localhost_browser_preflight(self) -> None:
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/studio/function-preview",
            method="OPTIONS",
            headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 204)
            self.assertEqual(resp.headers["Access-Control-Allow-Origin"], "http://localhost:5173")
            self.assertIn("POST", resp.headers["Access-Control-Allow-Methods"])

    def test_character_create_endpoint_replaces_fixed_player(self) -> None:
        result = self._post(
            "/api/character/create",
            {"template_id": "spellblade", "name": "Web旅者", "seed": 42},
        )
        self.assertEqual(result["character"]["template_id"], "spellblade")
        self.assertEqual(result["view"]["character"]["generated"], True)
        self.assertEqual(result["view"]["character"]["attributes"]["mag"], 15)
        self.assertEqual(result["view"]["health"]["max"], 96)
        self.assertEqual(self._get("/api/state")["actor"], result["view"]["actor"])

    def test_action_endpoint_moves_and_updates_view(self) -> None:
        result = self._post("/api/action", {"text": "go north"})
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["view"]["room"]["id"], "room.slum_alley")

    def test_deliver_quest_completes_through_http_api(self) -> None:
        self._post("/api/action", {"text": "go north"})
        self._post("/api/action", {"text": "go west"})
        accept = self._post("/api/action", {"text": "talk 工頭·老鐵 work"})
        self.assertIn("quest.transitioned", [e["type"] for e in accept["events"]])
        self._post("/api/action", {"text": "go east"})
        self._post("/api/action", {"text": "take item.firewood_bundle"})
        self._post("/api/action", {"text": "go west"})
        result = self._post("/api/action", {"text": "give item.firewood_bundle npc.foreman_laotie"})
        event_types = [e["type"] for e in result["events"]]
        self.assertIn("quest.transitioned", event_types)
        self.assertIn("quest.completed", event_types)
        quest = next(q for q in result["view"]["quests"] if q["id"] == "quest.find_work")
        self.assertEqual(quest["state"], "completed")
        self.assertEqual(result["view"]["wallet"]["currency"], 15)
        self.assertIn("這座城暫時承認了你的存在", result["view"]["room"]["description"])

    def test_talk_endpoint_returns_authored_dialogue_event(self) -> None:
        result = self._post("/api/action", {"text": "talk 老登記官 city"})
        self.assertEqual(result["status"], "completed")
        self.assertIn("北邊的關卡", result["message"])
        response = next(event for event in result["events"] if event["type"] == "dialogue.responded")
        self.assertEqual(response["payload"]["dialogue_id"], "dialogue.registration_clerk.city")


if __name__ == "__main__":
    unittest.main()
