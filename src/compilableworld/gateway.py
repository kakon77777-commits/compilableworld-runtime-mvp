from __future__ import annotations

import json
import shlex
from dataclasses import dataclass
from typing import Protocol

from .kernel import WorldRuntime
from .models import ActionIR


class IntentParser(Protocol):
    def parse(self, text: str, actor_id: str, runtime: WorldRuntime) -> ActionIR: ...


@dataclass
class DeterministicIntentParser:
    """Replaceable reference parser. An AI adapter must return the same ActionIR."""

    aliases = {"n": "north", "s": "south", "e": "east", "w": "west", "u": "up", "d": "down"}

    def parse(self, text: str, actor_id: str, runtime: WorldRuntime) -> ActionIR:
        parts = shlex.split(text.strip())
        if not parts:
            return ActionIR(actor_id, "look")
        verb = parts[0].lower()
        if verb in self.aliases:
            return ActionIR(actor_id, "move", args={"direction": self.aliases[verb]})
        if verb in {"go", "move"}:
            return ActionIR(actor_id, "move", args={"direction": parts[1].lower() if len(parts) > 1 else ""})
        if verb == "look":
            return ActionIR(actor_id, "look")
        if verb in {"i", "inv", "inventory"}:
            return ActionIR(actor_id, "inventory")
        if verb in {"take", "get", "drop", "open", "unlock", "attack"}:
            target = parts[1] if len(parts) > 1 else None
            return ActionIR(actor_id, "take" if verb == "get" else verb, target_id=target)
        if verb in {"status", "quests"}:
            return ActionIR(actor_id, verb)
        if verb == "say":
            return ActionIR(actor_id, "say", args={"text": " ".join(parts[1:])})
        raise ValueError(f"無法解析指令: {verb}")


class TerminalGateway:
    def __init__(self, runtime: WorldRuntime, actor_id: str, parser: IntentParser | None = None) -> None:
        self.runtime = runtime
        self.actor_id = actor_id
        self.parser = parser or DeterministicIntentParser()

    def run(self) -> None:
        print(f"CompilableWorld Runtime {self.runtime.package['manifest']['runtime_version']}")
        print("輸入 help 查看指令；quit 離開。")
        self._execute("look")
        while True:
            try:
                text = input("cw> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not text:
                continue
            if text in {"quit", "exit"}:
                break
            if text == "help":
                print("look | n/s/e/w | go DIR | take/drop ID | open/unlock ID | inventory | attack ID | say TEXT | status | quests | tick [N] | events | diag | save FILE | load FILE")
                continue
            if text.startswith("tick"):
                parts = text.split()
                receipts = self.runtime.advance(int(parts[1]) if len(parts) > 1 else 1)
                print(f"tick={self.runtime.scheduler.tick}; executed={len(receipts)}")
                continue
            if text == "events":
                for event in self.runtime.event_log.events[-10:]:
                    print(f"[{event.timestamp_tick}] {event.event_type} {json.dumps(event.payload, ensure_ascii=False)}")
                continue
            if text == "diag":
                print(json.dumps(self.runtime.diagnostics(), ensure_ascii=False, indent=2))
                continue
            if text.startswith("save "):
                self.runtime.save_snapshot(text[5:].strip())
                print("Snapshot 已儲存。")
                continue
            if text.startswith("load "):
                self.runtime.load_snapshot(text[5:].strip())
                print("Snapshot 已載入。")
                continue
            self._execute(text)

    def _execute(self, text: str) -> None:
        try:
            action = self.parser.parse(text, self.actor_id, self.runtime)
            receipt = self.runtime.submit(action)
            print(receipt.message)
            if action.verb in {"look", "move"} and receipt.status.value == "completed":
                self._render_room()
        except (ValueError, IndexError) as exc:
            print(f"輸入錯誤: {exc}")

    def _render_room(self) -> None:
        room_id = self.runtime.state.get(self.actor_id, "position", "room")
        room = next(r for r in self.runtime.package["rooms"] if r["room_id"] == room_id)
        visible = [
            f"{e.name}({e.entity_id})" for e in self.runtime.registry.values()
            if e.entity_id != self.actor_id and self.runtime.state.get(e.entity_id, "position", "room") == room_id
        ]
        print(f"\n== {room['name']} ==\n{room['description']}")
        if visible:
            print("可見：" + "、".join(visible))

