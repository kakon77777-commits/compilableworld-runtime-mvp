# Scoped StateIR 執行契約 v0.1

本文件描述 CompilableWorld Runtime 已落地的非 Quest 階層狀態機。它把原本只有初始值的 World／Region／Scene 階層狀態，擴充為 World／Region／Scene／Entity／System 五種可編譯、可執行、可快照與可重播的 StateIR。

## 1. Authoring 與所有權

來源檔使用 `compilableworld.state-machines/v0.1`，並由 `schemas/state-machines.v0.1.schema.json` 約束。每台機器必須宣告：

- `state_machine_id`、`title`；
- `owner_scope` 與 `owner_id`；
- `states`、`initial_state`；
- `persistence: runtime`；
- `visibility`；
- `authority: state_machine.core`；
- 至少一條 bounded transition。

owner 與 Runtime 儲存位置的對應如下：

| owner scope | 編譯期驗證 | StateStore path |
|---|---|---|
| `world` | `owner_id` 必須是 `world` 或 manifest world ID；編譯後正規化為 world ID | `<world_id>::fsm::<machine_id>` |
| `region` | 必須是 rooms 已宣告的 `region.*` | `<region_id>::fsm::<machine_id>` |
| `scene` | 必須引用已知 room | `<room_id>::fsm::<machine_id>` |
| `entity` | 必須引用已知 entity 或 item | `<entity_id>::fsm::<machine_id>` |
| `system` | 必須使用 `system.*` ID | `<system_id>::fsm::<machine_id>` |

同一 owner 下可以有多台機器，因為 state key 是 `state_machine_id`。舊版 `world.world_state_machines` 仍寫入 `<owner>::fsm::state`；新格式禁止使用 machine ID `state`，因此不會覆蓋舊存檔鍵。

## 2. 編譯期 fail-closed 規則

Compiler 除了確認 JSON 結構，也會驗證：

- 最多 1024 台機器、每台 2–256 個不重複狀態、1–4096 條 transition；
- owner 引用存在且 scope 正確；
- `initial_state` 與 transition 的 `from`／`to` 都在 states 內；
- 所有狀態由初始狀態可達；
- `completed`／`failed` 不可再有 outgoing transition；
- `on` 必須在共用 EventIR trigger 白名單內；
- `event_match` 最多 16 個有限 JSON scalar，欄位必須屬於該 EventIR 的 payload 契約；
- `priority` 介於 0 與 1,000,000；同一 `from/on/priority` 不得有歧義；
- manifest 必須明確啟用 `state_machine.core`。

未知欄位一律拒絕。因此 `guard`、`requirements`、`effects`、`reward`、任意 StateStore path 與 Python expression 都不會被悄悄執行。

## 3. Runtime 選邊與提交

收到 EventIR `E` 時，每台 StateIR 只從自己的目前狀態 `Q` 選取符合下列條件的 transition：

```text
transition.from == Q
transition.on == E.event_type
event_match(transition, E.payload) == true
```

若有多條候選，最高 `priority` 勝出；同優先權歧義已在編譯期拒絕。唯一允許的 effect 是：

```text
StateDelta(owner_id, "fsm", state_machine_id, "set", transition.to)
```

`state_machine.core` 沒有 ActionIR verb，不能被玩家或 AI 當作直接寫入入口。狀態變更一律經 `WorldRuntime.commit_reaction()`，成功後依序保留 `state.committed` 與 `fsm.transitioned`；進入 `completed` 或 `failed` 時再發出對應 terminal EventIR。

## 4. 跨層事件與 causation

不同 scope 不直接修改彼此狀態，只能透過 EventIR 串接。例如 Gray Crown 範例是：

```text
ActionIR(unlock)
  -> door.unlocked
  -> World fsm.completed
  -> Region fsm.transitioned
```

每個 reaction EventIR 的 `causation_id` 指向直接觸發它的前一個 EventIR，`correlation_id` 保留整條行為鏈。當 terminal FSM 觸發 actor quest 時，Runtime 會沿 EventLog 的 causation 鏈做最多 64 層的有界回溯，找回原始 ActionIR actor；循環、缺失或無法驗證的 provenance 會停止，不會猜測玩家。

owner scope 目前只決定狀態所有權與可見性，不是自動事件路由。Runtime 不會因為 `scene: room.vault` 就暗自判定某事件屬於該房間；authoring 必須用正式事件型別與 `event_match` 明確指定。這保留了可重播性，也避免目前尚未標準化的 location payload 被猜測成規則。

## 5. 可見性

StateIR 的 authoring visibility 會保守映射到 EventIR：

| StateIR visibility | EventIR visibility |
|---|---|
| `public`、`observable` | `public` |
| entity-owned `private` | `private`，target 為該 entity |
| 非 entity `private`、`inferred`、`system_only` | `audit` |

這個映射不會把推論、秘密或系統內部狀態公開。更細緻的每 actor belief／secret projection 仍需獨立契約。

## 6. Snapshot、Replay 與 Studio

- 初始狀態由 Compiler 寫入 Runtime Package 的 `initial_state`。
- Snapshot 保存每一個 scoped `fsm` cell 與版本。
- EventLog 保存 reaction 的 `state.committed` 與 `fsm.*` EventIR。
- Replay 使用已提交 Delta 還原結果，不重新抽樣或重跑自由文字。
- `package_overview()` 提供機器、owner、states、transitions 與 diagnostics。
- `runtime_overview()` 額外提供每台機器的 `current_state` 與 `state_version`。

Studio 投影仍是唯讀；正式修改必須回到 authoring source、Compiler、review 與部署流程，AI 不能直接寫 StateStore。

## 7. v0.1 明確不包含

- 本 StateIR 契約內的 Action-scope 狀態；可中斷／取消與 sequential phase checkpoint 已由獨立 `action-behaviors/v0.2` 契約提供，但 child Action Graph、resume／補償／平行子步驟仍未包含；
- 階層父子狀態、parallel region 與 history state；
- 自由形式 guard、腳本、任意 effect/reward；
- Runtime 對 Studio bounded random metadata 的自行抽樣；
- 隱式地理事件路由；
- AI 自動採納草稿或直接改寫 Runtime State。

驗證基線由 `tests/test_scoped_state_machine.py` 覆蓋五種 owner、跨層 chaining、terminal FSM 到 Quest、Snapshot、Replay、Studio projection、legacy seed 相容與 reaction rollback；完整測試為 285/285。
