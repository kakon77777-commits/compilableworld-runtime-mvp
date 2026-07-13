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
        self.assertIn("<title>CompilableWorld</title>", body)

    def test_state_endpoint_reflects_current_room(self) -> None:
        view = self._get("/api/state")
        self.assertEqual(view["room"]["id"], "room.registration_office")
        self.assertEqual(view["health"]["current"], 20)
        self.assertEqual(view["wallet"]["currency"], 0)

    def test_action_endpoint_moves_and_updates_view(self) -> None:
        result = self._post("/api/action", {"text": "go north"})
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["view"]["room"]["id"], "room.slum_alley")

    def test_deliver_quest_completes_through_http_api(self) -> None:
        self._post("/api/action", {"text": "go north"})
        self._post("/api/action", {"text": "take item.firewood_bundle"})
        self._post("/api/action", {"text": "go west"})
        result = self._post("/api/action", {"text": "give item.firewood_bundle npc.foreman_laotie"})
        event_types = [e["type"] for e in result["events"]]
        self.assertIn("quest.completed", event_types)
        quest = next(q for q in result["view"]["quests"] if q["id"] == "quest.find_work")
        self.assertEqual(quest["state"], "completed")
        self.assertEqual(result["view"]["wallet"]["currency"], 15)


if __name__ == "__main__":
    unittest.main()
