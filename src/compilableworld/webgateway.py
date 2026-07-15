from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .gateway import DeterministicIntentParser
from .kernel import WorldRuntime
from .models import EventIR
from .narrative import render_room_description
from .player_generation import generate_character
from .studio import function_catalog, function_preview, runtime_overview, schema_catalog
from .studio_mapping import StudioMappingError, suggest_studio_mapping, validate_studio_mapping
from .studio_world_ir import import_eveglyph_text

OPPOSITES = {"north": "south", "south": "north", "east": "west", "west": "east", "up": "down", "down": "up"}
MAX_STUDIO_IMPORT_BYTES = 512 * 1024


def _truth(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _door_state(runtime: WorldRuntime, door_id: str) -> dict[str, Any]:
    return {
        "id": door_id,
        "locked": runtime.state.get(door_id, "door", "locked", False),
        "open": runtime.state.get(door_id, "door", "open", False),
    }


def _available_exits(runtime: WorldRuntime, room_id: str) -> list[dict[str, Any]]:
    exits: list[dict[str, Any]] = []
    for edge in runtime.package["exits"]:
        door = edge.get("door_entity", "").strip()
        if edge["from_room"] == room_id:
            entry = {"direction": edge["direction"].lower(), "to_room": edge["to_room"]}
        elif _truth(edge.get("bidirectional", "false")) and edge["to_room"] == room_id:
            reverse = OPPOSITES.get(edge["direction"].lower())
            if not reverse:
                continue
            entry = {"direction": reverse, "to_room": edge["from_room"]}
        else:
            continue
        if door:
            entry["door"] = _door_state(runtime, door)
        exits.append(entry)
    return exits


def build_view_model(runtime: WorldRuntime, actor_id: str) -> dict[str, Any]:
    """Read-only projection (paper 07 §6.5): World state -> View Model.
    Never called from a module's evaluate() — UI-side only, no write path."""
    room_id = runtime.state.get(actor_id, "position", "room")
    room = next((r for r in runtime.package["rooms"] if r["room_id"] == room_id), None)
    visible = [
        {"id": e.entity_id, "name": e.name, "type": e.entity_type, "alive": runtime.state.get(e.entity_id, "status", "alive", True)}
        for e in runtime.registry.values()
        if e.entity_id != actor_id and runtime.state.get(e.entity_id, "position", "room") == room_id
    ]
    inventory = [
        {"id": e.entity_id, "name": e.name}
        for e in runtime.registry.values()
        if runtime.state.get(e.entity_id, "inventory", "carrier") == actor_id
    ]
    quests = [
        {
            "id": quest["quest_id"], "title": quest["title"],
            "state": runtime.state.get(actor_id, "quest", quest["quest_id"], quest.get("initial_state", "available")),
        }
        for quest in runtime.package.get("quests", [])
    ]
    actor = runtime.registry.get(actor_id)
    generation = actor.metadata.get("generation")
    attributes = {
        key: runtime.state.get(actor_id, "combat", key)
        for key in ("str", "con", "mag", "agi", "dex")
        if runtime.state.get(actor_id, "combat", key) is not None
    }
    return {
        "world_id": runtime.package["manifest"]["world_id"],
        "world_version": runtime.package["manifest"]["world_version"],
        "tick": runtime.scheduler.tick,
        "actor": actor_id,
        "character": {
            "id": actor_id,
            "name": actor.name,
            "generated": generation is not None,
            "generation": generation,
            "attributes": attributes,
            "phase_tier": runtime.state.get(actor_id, "combat", "phase_tier"),
        },
        "room": None if room is None else {
            "id": room["room_id"], "name": room["name"], "description": render_room_description(runtime, actor_id, room),
            "exits": _available_exits(runtime, room_id),
        },
        "visible_entities": visible,
        "inventory": inventory,
        "health": {"current": runtime.state.get(actor_id, "health", "current"), "max": runtime.state.get(actor_id, "health", "max")},
        "wallet": {"currency": runtime.state.get(actor_id, "wallet", "currency", 0)},
        "quests": quests,
    }


def _format_event(event: EventIR) -> dict[str, Any]:
    return {"tick": event.timestamp_tick, "type": event.event_type, "source": event.source, "payload": event.payload}


class _Handler(BaseHTTPRequestHandler):
    server_version = "CompilableWorldWeb/0.1"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - stdlib signature
        return  # keep the terminal clean; `diag`/event log already cover observability

    def _json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _cors_headers(self) -> None:
        origin = self.headers.get("Origin", "")
        if origin.startswith("http://localhost:") or origin.startswith("http://127.0.0.1:"):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Vary", "Origin")

    def do_OPTIONS(self) -> None:  # noqa: N802 - stdlib method name
        self.send_response(204)
        self._cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802 - stdlib method name
        if self.path in ("/", "/index.html"):
            body = INDEX_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/api/state":
            with self.server.lock:  # type: ignore[attr-defined]
                view = build_view_model(self.server.runtime, self.server.actor_id)  # type: ignore[attr-defined]
            self._json(200, view)
            return
        if self.path == "/api/character/templates":
            self._json(200, {"templates": self.server.runtime.player_templates()})  # type: ignore[attr-defined]
            return
        if self.path == "/api/studio/functions":
            with self.server.lock:  # type: ignore[attr-defined]
                catalog = function_catalog(self.server.runtime.package)  # type: ignore[attr-defined]
            self._json(200, catalog)
            return
        if self.path == "/api/studio/schemas":
            self._json(200, schema_catalog())
            return
        if self.path == "/api/studio/overview":
            with self.server.lock:  # type: ignore[attr-defined]
                overview = runtime_overview(self.server.runtime)  # type: ignore[attr-defined]
            self._json(200, overview)
            return
        self._json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802 - stdlib method name
        if self.path not in {
            "/api/action", "/api/character/create", "/api/studio/function-preview",
            "/api/studio/import", "/api/studio/validate-mapping",
        }:
            self._json(404, {"error": "not_found"})
            return
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length > MAX_STUDIO_IMPORT_BYTES:
            self._json(413, {"error": "request_too_large", "limit_bytes": MAX_STUDIO_IMPORT_BYTES})
            return
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(payload, dict):
                raise ValueError("request body must be an object")
            text = str(payload.get("text", "")).strip()
        except (json.JSONDecodeError, ValueError, TypeError):
            self._json(400, {"error": "invalid_json"})
            return
        if self.path == "/api/studio/import":
            source_text = payload.get("source_text")
            source_path = payload.get("source_path", "eveglyph-studio-draft.yaml")
            if not isinstance(source_text, str) or not source_text.strip():
                self._json(400, {"error": "invalid_studio_source", "message": "source_text must be a non-empty string"})
                return
            if not isinstance(source_path, str) or not source_path.strip() or len(source_path) > 256:
                self._json(400, {"error": "invalid_studio_source", "message": "source_path must be a short label"})
                return
            world_ir = import_eveglyph_text(source_text, source_path.strip())
            self._json(200, {
                "format": "compilableworld.studio-import-result/v0.1",
                "read_only": True,
                "world_ir": world_ir,
                "mapping_suggestion": suggest_studio_mapping(world_ir),
            })
            return
        if self.path == "/api/studio/validate-mapping":
            world_ir = payload.get("world_ir")
            mapping = payload.get("mapping")
            if not isinstance(world_ir, dict) or not isinstance(mapping, dict):
                self._json(400, {"error": "invalid_mapping_request", "message": "world_ir and mapping must be objects"})
                return
            try:
                report = validate_studio_mapping(world_ir, mapping)
            except (StudioMappingError, TypeError, KeyError, AttributeError) as exc:
                self._json(400, {"error": "invalid_mapping_request", "message": str(exc)})
                return
            self._json(200, {"format": "compilableworld.studio-mapping-validation-result/v0.1", "read_only": True, "report": report})
            return
        if self.path == "/api/studio/function-preview":
            with self.server.lock:  # type: ignore[attr-defined]
                try:
                    preview = function_preview(
                        self.server.runtime,  # type: ignore[attr-defined]
                        payload.get("function_id"),
                        payload.get("inputs", {}),
                    )
                except (TypeError, ValueError, KeyError) as exc:
                    self._json(400, {"error": "invalid_function_preview", "message": str(exc)})
                    return
            self._json(200, preview)
            return
        if self.path == "/api/character/create":
            with self.server.lock:  # type: ignore[attr-defined]
                runtime: WorldRuntime = self.server.runtime  # type: ignore[attr-defined]
                try:
                    raw_seed = payload.get("seed")
                    seed = None if raw_seed in (None, "") else int(raw_seed)
                    profile = generate_character(
                        template_id=str(payload.get("template_id", "balanced")),
                        name=payload.get("name"),
                        seed=seed,
                        randomize=bool(payload.get("random", False)),
                        attribute_overrides=payload.get("attributes"),
                        package=runtime.package,
                    )
                    actor_id = runtime.create_player(
                        profile,
                        replace_actor_id=self.server.actor_id,  # type: ignore[attr-defined]
                        replace_default=True,
                    )
                    self.server.actor_id = actor_id  # type: ignore[attr-defined]
                    view = build_view_model(runtime, actor_id)
                except (TypeError, ValueError, KeyError) as exc:
                    self._json(400, {"error": "invalid_character", "message": str(exc)})
                    return
            self._json(201, {"character": profile.to_dict(), "view": view})
            return
        if not text:
            self._json(400, {"error": "empty_command"})
            return
        with self.server.lock:  # type: ignore[attr-defined]
            runtime: WorldRuntime = self.server.runtime  # type: ignore[attr-defined]
            actor_id: str = self.server.actor_id  # type: ignore[attr-defined]
            before = len(runtime.event_log.events)
            try:
                action = DeterministicIntentParser().parse(text, actor_id, runtime)
                receipt = runtime.submit(action)
                message, status = receipt.message, receipt.status.value
            except (ValueError, IndexError) as exc:
                message, status = f"輸入錯誤: {exc}", "rejected"
            new_events = [_format_event(event) for event in runtime.event_log.events[before:]]
            view = build_view_model(runtime, actor_id)
        self._json(200, {"message": message, "status": status, "events": new_events, "view": view})


class WebGateway:
    """Additive UI Adapter (paper 07 §6.6): projects state, submits Action IR
    through the same pipeline as TerminalGateway, never touches StateStore
    directly. Stdlib-only (no WebSocket/Flask dep) — plain request/response
    fits a single-player, turn-based MUD without adding a supply-chain
    surface Neo doesn't need."""

    def __init__(self, runtime: WorldRuntime, actor_id: str, port: int = 8765) -> None:
        self.runtime = runtime
        self.actor_id = actor_id
        self.port = port

    def run(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", self.port), _Handler)
        server.runtime = self.runtime  # type: ignore[attr-defined]
        server.actor_id = self.actor_id  # type: ignore[attr-defined]
        server.lock = threading.Lock()  # type: ignore[attr-defined]
        print(f"CompilableWorld Web Gateway: http://127.0.0.1:{self.port}/")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


INDEX_HTML = r"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CompilableWorld Runtime</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body {
    margin: 0; font-family: "Noto Sans TC", "Segoe UI", sans-serif;
    background: #14161c; color: #dfe3ea; min-height: 100vh; display: flex; flex-direction: column;
  }
  header {
    display: flex; justify-content: space-between; align-items: baseline;
    padding: 0.75rem 1.25rem; background: #1c1f28; border-bottom: 1px solid #2c303c;
  }
  header h1 { font-size: 1.1rem; margin: 0; letter-spacing: 0.03em; }
  header span { font-family: monospace; color: #8891a7; font-size: 0.85rem; }
  main { display: flex; flex: 1; min-height: 0; }
  #scene { flex: 2; padding: 1.25rem; overflow-y: auto; }
  #room-name { margin: 0 0 0.5rem; color: #f2c94c; }
  #room-desc { line-height: 1.7; color: #c4c9d4; }
  .exit-row, .entity-row { display: flex; flex-wrap: wrap; gap: 0.5rem; margin: 0.75rem 0; }
  button {
    background: #262b38; color: #dfe3ea; border: 1px solid #3a4053; border-radius: 6px;
    padding: 0.4rem 0.75rem; font-size: 0.85rem; cursor: pointer;
  }
  button:hover { background: #323848; }
  button.locked { color: #6a7086; border-color: #3a4053; cursor: not-allowed; }
  button.danger { border-color: #7a3838; }
  button.accent { border-color: #4c7a4c; }
  #sidebar {
    flex: 1; min-width: 260px; max-width: 320px; padding: 1.25rem; background: #191c24;
    border-left: 1px solid #2c303c; overflow-y: auto;
  }
  #sidebar h3 { font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.08em; color: #8891a7; margin: 1.25rem 0 0.5rem; }
  .bar-track { background: #262b38; border-radius: 6px; overflow: hidden; height: 10px; }
  .bar-fill { background: #6fae6f; height: 100%; }
  #sidebar ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 0.4rem; }
  .item-row { display: flex; align-items: center; gap: 0.35rem; flex-wrap: wrap; font-size: 0.85rem; }
  .quest-row { font-size: 0.85rem; }
  .quest-available { color: #8891a7; }
  .quest-completed { color: #6fae6f; }
  select { background: #262b38; color: #dfe3ea; border: 1px solid #3a4053; border-radius: 6px; padding: 0.25rem; }
  .character-builder { display: grid; gap: 0.4rem; }
  .character-builder input { width: 100%; background: #10121a; color: #dfe3ea; border: 1px solid #3a4053; border-radius: 6px; padding: 0.35rem; }
  .character-builder button { width: 100%; }
  #character-summary { color: #8891a7; font-size: 0.8rem; line-height: 1.5; }
  #log {
    height: 30vh; overflow-y: auto; padding: 0.75rem 1.25rem; background: #10121780;
    border-top: 1px solid #2c303c; font-family: "Cascadia Code", monospace; font-size: 0.85rem;
  }
  #log p { margin: 0.15rem 0; }
  .log-quest { color: #f2c94c; }
  .log-error { color: #d97070; }
  #cmd-form { display: flex; gap: 0.5rem; padding: 0.75rem 1.25rem; background: #1c1f28; border-top: 1px solid #2c303c; }
  #cmd-input {
    flex: 1; background: #10121a; color: #dfe3ea; border: 1px solid #3a4053; border-radius: 6px;
    padding: 0.55rem 0.75rem; font-family: monospace; font-size: 0.9rem;
  }
</style>
</head>
<body>
  <header>
    <h1 id="world-title">CompilableWorld Runtime</h1>
    <span id="tick">tick 0</span>
  </header>
  <main>
    <section id="scene">
      <h2 id="room-name">…</h2>
      <p id="room-desc"></p>
      <div id="exits" class="exit-row"></div>
      <div id="entities" class="entity-row"></div>
    </section>
    <aside id="sidebar">
      <h3>角色生成</h3>
      <div class="character-builder">
        <div id="character-summary">載入中…</div>
        <select id="template-select"></select>
        <input id="character-name-input" placeholder="角色名稱（可留白）">
        <input id="character-seed-input" type="number" placeholder="Seed（可留白）">
        <button id="create-template-button" class="accent">套用模板</button>
        <button id="random-character-button">隨機生成</button>
      </div>
      <h3>生命值</h3>
      <div class="bar-track"><div id="health-bar" class="bar-fill" style="width:0%"></div></div>
      <div id="health-text" style="font-size:0.8rem;color:#8891a7;margin-top:0.25rem;"></div>
      <h3>貨幣</h3>
      <div id="wallet"></div>
      <h3>物品欄</h3>
      <ul id="inventory"></ul>
      <h3>任務</h3>
      <ul id="quests"></ul>
    </aside>
  </main>
  <section id="log"></section>
  <form id="cmd-form">
    <input id="cmd-input" autocomplete="off" placeholder="輸入指令，如 look / talk 老鐵 work / attack npc.xxx">
    <button type="submit">送出</button>
  </form>
<script>
const logEl = document.getElementById('log');
function appendLog(text, cls) {
  const p = document.createElement('p');
  if (cls) p.className = cls;
  p.textContent = text;
  logEl.appendChild(p);
  logEl.scrollTop = logEl.scrollHeight;
}

function describeEvent(ev) {
  if (ev.type === 'quest.transitioned') {
    appendLog(`>> 任務進度：${ev.payload.title} [${ev.payload.from} → ${ev.payload.to}]`, 'log-quest');
  } else if (ev.type === 'quest.completed') {
    const reward = ev.payload.reward || {};
    const note = reward.currency ? `，獲得 ${reward.currency} 貨幣` : '';
    appendLog(`>> 任務完成：${ev.payload.title}${note}`, 'log-quest');
  } else if (ev.type === 'quest.failed') {
    appendLog(`>> 任務失敗：${ev.payload.title}`, 'log-error');
  }
}

function render(view) {
  document.getElementById('world-title').textContent = view.world_id + ' v' + view.world_version;
  document.getElementById('tick').textContent = 'tick ' + view.tick;
  const character = view.character || {};
  const generation = character.generation || {};
  const attrs = character.attributes || {};
  document.getElementById('character-summary').textContent =
    `${character.name || character.id || ''} · ${generation.template_id || 'legacy'} · ` +
    `STR ${attrs.str ?? '—'} / CON ${attrs.con ?? '—'} / MAG ${attrs.mag ?? '—'} / AGI ${attrs.agi ?? '—'} / DEX ${attrs.dex ?? '—'}`;

  const room = view.room;
  document.getElementById('room-name').textContent = room ? room.name : '（未知位置）';
  document.getElementById('room-desc').textContent = room ? room.description : '';

  const exitsEl = document.getElementById('exits');
  exitsEl.innerHTML = '';
  (room ? room.exits : []).forEach(exit => {
    const btn = document.createElement('button');
    const locked = exit.door && exit.door.locked;
    btn.textContent = exit.direction + (exit.door ? (locked ? ' 🔒' : ' 🚪') : '');
    btn.onclick = () => sendCommand('go ' + exit.direction);
    exitsEl.appendChild(btn);
  });

  const entitiesEl = document.getElementById('entities');
  entitiesEl.innerHTML = '';
  view.visible_entities.forEach(entity => {
    const row = document.createElement('span');
    row.className = 'item-row';
    row.textContent = entity.name + (entity.alive === false ? '（已死亡）' : '') + '（' + entity.id + '）';
    if (entity.type === 'item') {
      const take = document.createElement('button');
      take.textContent = '拿取';
      take.onclick = () => sendCommand('take ' + entity.id);
      row.appendChild(take);
    }
    if ((entity.type === 'character' || entity.type === 'creature') && entity.alive !== false) {
      const talk = document.createElement('button');
      talk.textContent = '交談';
      talk.onclick = () => sendCommand('talk ' + entity.id);
      row.appendChild(talk);
    }
    entitiesEl.appendChild(row);
  });

  const hp = view.health || {};
  const pct = hp.max ? Math.max(0, Math.min(100, 100 * hp.current / hp.max)) : 0;
  document.getElementById('health-bar').style.width = pct + '%';
  document.getElementById('health-text').textContent = (hp.current ?? '—') + ' / ' + (hp.max ?? '—');
  document.getElementById('wallet').textContent = (view.wallet.currency ?? 0) + ' 貨幣';

  const npcTargets = view.visible_entities.filter(e => e.type === 'character' || e.type === 'creature');
  const invEl = document.getElementById('inventory');
  invEl.innerHTML = '';
  if (view.inventory.length === 0) {
    invEl.innerHTML = '<li style="color:#565c70;">空</li>';
  }
  view.inventory.forEach(item => {
    const li = document.createElement('li');
    li.className = 'item-row';
    li.textContent = item.name + ' ';
    const drop = document.createElement('button');
    drop.textContent = '放下';
    drop.onclick = () => sendCommand('drop ' + item.id);
    li.appendChild(drop);
    if (npcTargets.length > 0) {
      const select = document.createElement('select');
      npcTargets.forEach(t => {
        const opt = document.createElement('option');
        opt.value = t.id; opt.textContent = t.name;
        select.appendChild(opt);
      });
      const give = document.createElement('button');
      give.className = 'accent';
      give.textContent = '交付';
      give.onclick = () => sendCommand('give ' + item.id + ' ' + select.value);
      li.appendChild(select);
      li.appendChild(give);
    }
    invEl.appendChild(li);
  });

  const questEl = document.getElementById('quests');
  questEl.innerHTML = '';
  view.quests.forEach(quest => {
    const li = document.createElement('li');
    li.className = 'quest-row quest-' + quest.state;
    li.textContent = quest.title + ' [' + quest.state + ']';
    questEl.appendChild(li);
  });
}

async function sendCommand(text) {
  const res = await fetch('/api/action', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({text}),
  });
  const data = await res.json();
  appendLog('> ' + text);
  appendLog(data.message, data.status === 'failed' || data.status === 'rejected' ? 'log-error' : null);
  (data.events || []).forEach(describeEvent);
  if (data.view) render(data.view);
}

async function loadCharacterTemplates() {
  const res = await fetch('/api/character/templates');
  const data = await res.json();
  const select = document.getElementById('template-select');
  (data.templates || []).forEach(template => {
    const option = document.createElement('option');
    option.value = template.template_id;
    option.textContent = template.name + ' — ' + template.description;
    select.appendChild(option);
  });
}

async function createCharacter(random) {
  const seedText = document.getElementById('character-seed-input').value.trim();
  const payload = {
    template_id: document.getElementById('template-select').value || 'balanced',
    name: document.getElementById('character-name-input').value.trim(),
    random,
  };
  if (seedText) payload.seed = Number(seedText);
  const res = await fetch('/api/character/create', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) {
    appendLog(data.message || '角色生成失敗', 'log-error');
    return;
  }
  appendLog('已建立新的玩家角色：' + data.character.name);
  render(data.view);
}

document.getElementById('create-template-button').onclick = () => createCharacter(false);
document.getElementById('random-character-button').onclick = () => createCharacter(true);

document.getElementById('cmd-form').addEventListener('submit', ev => {
  ev.preventDefault();
  const input = document.getElementById('cmd-input');
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  sendCommand(text);
});

fetch('/api/state').then(r => r.json()).then(view => { render(view); appendLog('世界已載入。'); });
loadCharacterTemplates().catch(() => appendLog('角色模板載入失敗', 'log-error'));
</script>
</body>
</html>
"""
