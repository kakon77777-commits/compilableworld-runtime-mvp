# Scoped StateIR 執行契約 v0.3

本文件描述 CompilableWorld Runtime 已落地的非 Quest 階層狀態機。它把原本只有初始值的 World／Region／Scene 階層狀態，擴充為 World／Region／Scene／Entity／System 五種可編譯、可執行、可快照與可重播的 StateIR。v0.3 在 v0.2 的 bounded StateStore AND conditions 上加入 deterministic tick timer；沒有加入牆鐘、背景執行緒、自由 guard、任意 effect 或第二個狀態真實來源。

## 1. Authoring 與所有權

新來源檔使用 `compilableworld.state-machines/v0.3`，並由 `schemas/state-machines.v0.3.schema.json` 約束；v0.1 無條件事件來源與 v0.2 bounded-condition 事件來源仍可編譯。Compiler 會將 v0.1 transition 正規化為 `when: []`，但不替舊來源假造 timer。每台機器必須宣告：

- `state_machine_id`、`title`；
- `owner_scope` 與 `owner_id`；
- `states`、`initial_state`；
- `persistence: runtime`；
- `visibility`；
- `authority: state_machine.core`；
- 至少一條 bounded transition。

v0.3 transition 必須明確提供 `when` 陣列，並且只能選一種 trigger：正式 EventIR 的 `on`，或 1–1,000,000 的 `after_ticks`。Timer transition 不得同時宣告 `on` 或 `event_match`。每條 transition 最多 16 個條件，採 AND；每個條件固定包含 `condition_id`、`subject`、`namespace`、`key`、`operator` 與 JSON finite scalar `value`。`subject` 只允許：

- `owner`：讀取該機器自己的 `owner_id`；
- `actor`：讀取由觸發 EventIR 的 bounded causation chain 驗證出的 ActionIR actor。

Timer 沒有 ActionIR causation，因此 timer transition 的條件只允許 `owner`；Compiler 直接拒絕 `subject: actor`，不會在執行期猜測玩家。

可讀 namespace 限於 `combat`、`door`、`exploration`、`fsm`、`health`、`inventory`、`magic`、`position`、`quest`、`status`、`wallet`。operator 限於 `equals`、`not_equals` 與四種數值大小比較；數值比較拒絕 boolean，等值比較不把 `true/false` 當成 `1/0`。

owner 與 Runtime 儲存位置的對應如下：

| owner scope | 編譯期驗證 | StateStore path |
|---|---|---|
| `world` | `owner_id` 必須是 `world` 或 manifest world ID；編譯後正規化為 world ID | `<world_id>::fsm::<machine_id>` |
| `region` | 必須是 rooms 已宣告的 `region.*` | `<region_id>::fsm::<machine_id>` |
| `scene` | 必須引用已知 room | `<room_id>::fsm::<machine_id>` |
| `entity` | 必須引用已知 entity 或 item | `<entity_id>::fsm::<machine_id>` |
| `system` | 必須使用 `system.*` ID | `<system_id>::fsm::<machine_id>` |

同一 owner 下可以有多台機器，因為 state key 是 `state_machine_id`。舊版 `world.world_state_machines` 仍寫入 `<owner>::fsm::state`；新格式禁止使用 machine ID `state`，因此不會覆蓋舊存檔鍵。

只要一台機器宣告 timer，Compiler 會另外建立保留的 `<owner>::fsm_runtime::<state_machine_id>` 整數 State Cell，記錄目前 state 的 `entered_tick`。它只能由 `state_machine.core` 與狀態轉移在同一筆原子交易更新；Authoring、Studio、AI 與一般條件不能寫入或讀取這個保留 namespace。

## 2. 編譯期 fail-closed 規則

Compiler 除了確認 JSON 結構，也會驗證：

- 最多 1024 台機器、每台 2–256 個不重複狀態、1–4096 條 transition；
- owner 引用存在且 scope 正確；
- `initial_state` 與 transition 的 `from`／`to` 都在 states 內；
- 所有狀態由初始狀態可達；
- `completed`／`failed` 不可再有 outgoing transition；
- `on` 必須在共用 EventIR trigger 白名單內；
- `event_match` 最多 16 個有限 JSON scalar，欄位必須屬於該 EventIR 的 payload 契約；
- v0.2／v0.3 `when` 最多 16 個條件，`condition_id` 在同一台機器內唯一，subject／namespace／operator 必須在白名單內；
- v0.3 每條 transition 必須且只能宣告 `on` 或 `after_ticks`；timer tick 必須是 bounded positive integer，且不得搭配 `event_match` 或 actor condition；
- 非等值 operator 的 `value` 必須是有限 number，不能是 boolean；
- `priority` 介於 0 與 1,000,000；同一 `from/on/priority` 或 `from/timer/priority` 不得有歧義（timer 即使 delay 不同，elapsed 後仍可能重疊）；
- manifest 必須明確啟用 `state_machine.core`。

未知欄位一律拒絕。因此 `guard`、`requirements`、`effects`、`reward`、任意 StateStore path 與 Python expression 都不會被悄悄執行。v0.1 來源若偷偷加入 `when`，或 v0.1／v0.2 來源加入 `after_ticks`，都會被拒絕；作者必須明確升級格式與 manifest schema ID。

## 3. Runtime 選邊與提交

收到 EventIR `E` 時，每台 StateIR 只從自己的目前狀態 `Q` 選取符合下列條件的 transition：

```text
transition.from == Q
transition.on == E.event_type
event_match(transition, E.payload) == true
AND(state_condition(transition.when, StateStore, owner, verified_actor)) == true
```

Runtime 先完成 EventIR、payload 與全部條件篩選，再從剩餘候選選最高 `priority`；所以高優先邊條件失敗時，可由較低優先的明確 fallback 接手。同優先權歧義已在編譯期拒絕。

Timer transition 使用同一個 Kernel scheduler tick，沒有第二套時鐘：

```text
eligible_tick = entered_tick + after_ticks
current_tick >= eligible_tick
AND(owner_state_conditions) == true
```

條件尚未成立時，timer 保持 eligible，而不是遺失、忙等或偷偷改寫狀態；條件之後成立時，再由所有 eligible candidate 中的最高 `priority` 唯一選邊。每個 tick 的固定順序是 Action checkpoint 提交與事件反應、StateIR timer batch、到期 Action terminal execution。所有同 tick timer 先從同一份 pre-commit StateStore 選邊，再以 owner／machine ID 排序成一筆 bounded StateDelta／EventIR batch。

條件讀取沒有型別轉換。缺少 actor provenance、缺少 State Cell、未知 subject／namespace／operator、非有限數字或錯誤型別一律回傳 false，也不發出帶有實際秘密值的診斷 EventIR。條件本身不寫入 StateStore，不消耗隨機數，也不因 UI 讀取而重算世界狀態。

事件型與 timer 型 transition 唯一允許的 effect 是自己的狀態 Cell；有 timer 的機器會在同一交易更新保留 entry-tick Cell：

```text
StateDelta(owner_id, "fsm", state_machine_id, "set", transition.to)
StateDelta(owner_id, "fsm_runtime", state_machine_id, "set", current_tick)  # timer machine only
```

`state_machine.core` 沒有 ActionIR verb，不能被玩家或 AI 當作直接寫入入口。狀態變更一律經 `WorldRuntime.commit_reaction()`；事件轉移成功後依序保留 `state.committed` 與 `fsm.transitioned`，timer 轉移則依序保留 `state.committed`、`fsm.timer_elapsed` 與 `fsm.transitioned`。進入 `completed` 或 `failed` 時再發出對應 terminal EventIR。

## 4. 跨層事件與 causation

不同 scope 不直接修改彼此狀態，只能透過 EventIR 串接。例如 Gray Crown 範例是：

```text
ActionIR(unlock)
  -> door.unlocked
  -> World fsm.completed
  -> Region fsm.transitioned
```

每個 reaction EventIR 的 `causation_id` 指向直接觸發它的前一個 EventIR，`correlation_id` 保留整條行為鏈。當 terminal FSM 觸發 actor quest 時，Runtime 會沿 EventLog 的 causation 鏈做最多 64 層的有界回溯，找回原始 ActionIR actor；循環、缺失或無法驗證的 provenance 會停止，不會猜測玩家。

Timer 沒有外部 cause。`fsm.timer_elapsed` 以自己的 event ID 建立 correlation root，payload 明確記錄 `after_ticks`、`entered_tick`、`eligible_at_tick` 與 `fired_at_tick`；後續 `fsm.transitioned`／terminal event 的 `causation_id` 指向該 timer event。Replay 會驗證 timer payload 與已編譯 transition 一致。

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
- Snapshot v0.6 透過既有 StateStore 一併保存 `fsm_runtime` entry tick，因此不需要新增 Snapshot 格式或第二份 timer queue。
- EventLog 保存 reaction 的 `state.committed` 與 `fsm.*` EventIR。
- Replay 使用已提交 Delta 還原結果，不重新抽樣或重跑自由文字。
- `package_overview()` 提供機器、owner、states、transitions 與 diagnostics。
- Studio transition projection 會顯示 trigger kind、`on`／`after_ticks` 與完整 authored `when` 定義，供人工審查；它仍是唯讀投影。
- `runtime_overview()` 額外提供每台機器的 `current_state`、`state_version`、`entered_tick` 與目前 state 的 pending timer／剩餘 tick。

Studio 投影仍是唯讀；正式修改必須回到 authoring source、Compiler、review 與部署流程，AI 不能直接寫 StateStore。

## 7. v0.3 明確不包含

- 本 StateIR 契約內的 Action-scope 狀態；可中斷／取消、compile-time static phase DAG、sticky priority route、單一路徑 merge、非遞迴 primitive child sequence、bounded phase gates 與 fixed-interval retry/deadline 已由獨立 `action-behaviors/v0.7` 契約提供，但 dynamic／recursive／nested Action Graph、resume／補償／平行子步驟與同步 join 仍未包含；
- 階層父子狀態、parallel region 與 history state；
- 牆鐘、日曆、多速率 clock、cron、背景 thread、週期 timer、timer cancellation 與玩家／MCP 直接控制權威時間；
- OR／NOT 條件群組、自由形式 guard、腳本、任意 effect/reward；
- Runtime 對 Studio bounded random metadata 的自行抽樣；
- 隱式地理事件路由；
- AI 自動採納草稿或直接改寫 Runtime State。

驗證基線由 `tests/test_scoped_state_machine.py` 覆蓋五種 owner、跨層 chaining、terminal FSM 到 Quest、owner／actor AND conditions、嚴格純量型別、event／timer priority、v0.1／v0.2 來源相容、entry tick、延後條件、Snapshot、Replay timer validation、Studio countdown projection、legacy seed 相容與 reaction rollback。完整測試為 324/324，另有 52 個 subtests。
