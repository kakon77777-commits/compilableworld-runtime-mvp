from __future__ import annotations

import json
import shlex
from dataclasses import dataclass
from typing import Protocol

from .kernel import RuntimeErrorBase, WorldRuntime
from .models import ActionIR, EventIR
from .narrative import render_room_description


class IntentParser(Protocol):
    def parse(self, text: str, actor_id: str, runtime: WorldRuntime) -> ActionIR: ...


@dataclass
class DeterministicIntentParser:
    """Replaceable reference parser. An AI adapter must return the same ActionIR."""

    aliases = {"n": "north", "s": "south", "e": "east", "w": "west", "u": "up", "d": "down"}
    directions = {"north", "south", "east", "west", "up", "down"}

    def parse(self, text: str, actor_id: str, runtime: WorldRuntime) -> ActionIR:
        parts = shlex.split(text.strip())
        if not parts:
            return ActionIR(actor_id, "look")
        verb = parts[0].lower()
        if verb in self.aliases:
            return ActionIR(actor_id, "move", args={"direction": self.aliases[verb]})
        if verb in self.directions:
            return ActionIR(actor_id, "move", args={"direction": verb})
        if verb in {"go", "move"}:
            return ActionIR(actor_id, "move", args={"direction": parts[1].lower() if len(parts) > 1 else ""})
        if verb == "look":
            return ActionIR(actor_id, "look")
        if verb == "search":
            return ActionIR(actor_id, "search")
        if verb in {"i", "inv", "inventory"}:
            return ActionIR(actor_id, "inventory")
        if verb in {"take", "get", "drop", "open", "unlock", "attack"}:
            target = self._resolve(parts[1] if len(parts) > 1 else None, actor_id, runtime)
            return ActionIR(actor_id, "take" if verb == "get" else verb, target_id=target)
        if verb in {"talk", "ask"}:
            target = self._resolve(parts[1] if len(parts) > 1 else None, actor_id, runtime)
            topic = parts[2].lower() if len(parts) > 2 else "default"
            return ActionIR(actor_id, "talk", target_id=target, args={"topic": topic})
        if verb == "give":
            item = self._resolve(parts[1] if len(parts) > 1 else None, actor_id, runtime)
            recipient = self._resolve(parts[2] if len(parts) > 2 else None, actor_id, runtime)
            return ActionIR(actor_id, "give", target_id=item, args={"recipient": recipient})
        if verb in {"status", "quests"}:
            return ActionIR(actor_id, verb)
        if verb == "say":
            return ActionIR(actor_id, "say", args={"text": " ".join(parts[1:])})
        if verb == "cast":
            return ActionIR(actor_id, "cast", args={"spell": parts[1] if len(parts) > 1 else ""})
        raise ValueError(f"無法解析指令: {verb}")

    @staticmethod
    def _resolve(token: str | None, actor_id: str, runtime: WorldRuntime) -> str | None:
        """A real player only ever sees display names ("老鐵"), never internal
        IDs ("npc.foreman_laotie") — found by an actual playtest, not assumed.
        Falls through to the raw token (unresolved) on no-match/ambiguous, so
        downstream modules give their normal "not found" message rather than
        silently guessing the wrong target."""
        if not token or runtime.registry.contains(token):
            return token
        room = runtime.state.get(actor_id, "position", "room")
        candidates = [
            e for e in runtime.registry.values()
            if e.entity_id != actor_id and (
                runtime.state.get(e.entity_id, "position", "room") == room
                or runtime.state.get(e.entity_id, "inventory", "carrier") == actor_id
            )
        ]
        exact = [e for e in candidates if e.name == token]
        if len(exact) == 1:
            return exact[0].entity_id
        partial = [e for e in candidates if token in e.name]
        if len(partial) == 1:
            return partial[0].entity_id
        return token


class TerminalGateway:
    def __init__(self, runtime: WorldRuntime, actor_id: str, parser: IntentParser | None = None) -> None:
        self.runtime = runtime
        self.actor_id = actor_id
        self.parser = parser or DeterministicIntentParser()
        self.runtime.events.subscribe("quest.transitioned", self._on_quest_transitioned)
        self.runtime.events.subscribe("quest.completed", self._on_quest_completed)
        self.runtime.events.subscribe("quest.failed", self._on_quest_failed)
        self.runtime.events.subscribe("action.progressed", self._on_action_progressed)
        self.runtime.events.subscribe("action.retry_scheduled", self._on_action_retry_scheduled)
        self.runtime.events.subscribe("action.child_completed", self._on_action_child_completed)
        self.runtime.events.subscribe("action.child_failed", self._on_action_child_failed)

    def _on_action_child_completed(self, event) -> None:
        if event.target != self.actor_id:
            return
        print(
            f">> 子步驟完成：{event.payload['step_id']} "
            f"({event.payload['child_verb']})"
        )

    def _on_action_child_failed(self, event) -> None:
        if event.target != self.actor_id:
            return
        print(
            f">> 子步驟失敗：{event.payload['step_id']}："
            f"{event.payload.get('reason', 'unknown reason')}"
        )

    def _on_action_progressed(self, event) -> None:
        if event.target != self.actor_id:
            return
        print(
            f">> 行為進度：{event.payload['phase_title']} "
            f"[{event.payload['completed_phases']}/{event.payload['total_phases']}]"
        )

    def _on_action_retry_scheduled(self, event) -> None:
        if event.target != self.actor_id:
            return
        print(
            f">> 行為等待條件：{event.payload['phase_id']}，"
            f"retry {event.payload['attempt']}/{event.payload['max_attempts']} "
            f"at tick {event.payload['retry_at_tick']}"
        )

    def _on_quest_transitioned(self, event) -> None:
        if event.target != self.actor_id:
            return
        print(f">> 任務進度：{event.payload['title']} [{event.payload['from']} → {event.payload['to']}]")

    def _on_quest_completed(self, event) -> None:
        if event.target != self.actor_id:
            return
        reward = event.payload.get("reward") or {}
        note = f"，獲得 {reward['currency']} 貨幣" if reward.get("currency") else ""
        print(f">> 任務完成：{event.payload['title']}{note}")

    def _on_quest_failed(self, event) -> None:
        if event.target != self.actor_id:
            return
        print(f">> 任務失敗：{event.payload['title']}")

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
                print("look | search | n/s/e/w/north/south/east/west/up/down | go DIR | take/drop/open/unlock/attack 名稱或ID | talk/ask 對象 [topic] | give 物品 對象 | cast 法術名 | inventory | say TEXT | status | quests | tick [N] | pending | cancel ACTION_ID | events | diag | save FILE | load FILE")
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
            if text == "pending":
                pending = self.runtime.pending_actions(self.actor_id)
                print(json.dumps(pending, ensure_ascii=False, indent=2) if pending else "沒有待執行行為。")
                continue
            if text.startswith("cancel "):
                try:
                    receipt = self.runtime.cancel_action(self.actor_id, text[7:].strip())
                    print(receipt.message)
                except RuntimeErrorBase as exc:
                    print(f"取消失敗: {exc}")
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
        visible = []
        for e in self.runtime.registry.values():
            if e.entity_id == self.actor_id or self.runtime.state.get(e.entity_id, "position", "room") != room_id:
                continue
            dead = "（已死亡）" if not self.runtime.state.get(e.entity_id, "status", "alive", True) else ""
            visible.append(f"{e.name}{dead}({e.entity_id})")
        print(f"\n== {room['name']} ==\n{render_room_description(self.runtime, self.actor_id, room)}")
        if visible:
            print("可見：" + "、".join(visible))
