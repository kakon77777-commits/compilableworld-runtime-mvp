# Scoped StateIR 執行契約 v0.6

本文件描述 CompilableWorld Runtime 已落地的非 Quest 階層狀態機。它把原本只有初始值的 World／Region／Scene 階層狀態，擴充為 World／Region／Scene／Entity／System 五種可編譯、可執行、可快照與可重播的 StateIR。v0.6 在 v0.5 single-active-leaf compound state 上加入 bounded `all`／`any`／`not` condition expression；沒有加入 parallel region、history state、任意 entry／exit effect、牆鐘、自由 guard 或第二個狀態真實來源。

## 1. Authoring 與所有權

新來源檔使用 `compilableworld.state-machines/v0.6`，並由 `schemas/state-machines.v0.6.schema.json` 約束；v0.1–v0.5 來源仍可編譯。v0.1 transition 會正規化為 `when: []`，v0.2–v0.5 保留舊式 AND list，v0.1–v0.4 另正規化成空 hierarchy；Compiler 不替舊來源假造 timer、非終態依賴、compound state 或 condition group。每台機器必須宣告：

- `state_machine_id`、`title`；
- `owner_scope` 與 `owner_id`；
- `states`、`initial_state`；
- `hierarchy.parent_by_state` 與 `hierarchy.initial_child_by_state`；平面機器兩者都是空物件；
- `persistence: runtime`；
- `visibility`；
- `authority: state_machine.core`；
- 至少一條 bounded transition。

v0.6 transition 必須明確提供 `when` condition expression，並且只能選一種 trigger：正式 EventIR 的 `on`，或 1–1,000,000 的 `after_ticks`。Timer transition 不得同時宣告 `on` 或 `event_match`。每個 leaf 條件固定包含 `condition_id`、`subject`、`namespace`、`key`、`operator` 與 JSON finite scalar `value`。`subject` 只允許：

- `owner`：讀取該機器自己的 `owner_id`；
- `actor`：讀取由觸發 EventIR 的 bounded causation chain 驗證出的 ActionIR actor。

Timer 沒有 ActionIR causation，因此 timer transition 的條件只允許 `owner`；Compiler 直接拒絕 `subject: actor`，不會在執行期猜測玩家。

可讀 namespace 限於 `combat`、`door`、`exploration`、`fsm`、`health`、`inventory`、`magic`、`position`、`quest`、`status`、`wallet`。operator 限於 `equals`、`not_equals` 與四種數值大小比較；數值比較拒絕 boolean，等值比較不把 `true/false` 當成 `1/0`。

### 1.1 Bounded condition groups

`when` 可以是單一 leaf，或精確只含一個 operator 的群組：`{"all": [...]}`、`{"any": [...]}`、`{"not": expression}`。空 `all` 代表無條件成立；`any` 必須至少有一個 child；`not` 只接受一個 expression。每個 `all`／`any` 最多 16 個 child，每條 transition 最多 4 層群組、64 個 expression node 與 32 個 leaf condition；`condition_id` 在同一台機器內仍必須唯一。

判定採三值語義：leaf 結果為 true、false 或 unknown。`all` 遇到 false 為 false，否則有 unknown 就是 unknown；`any` 遇到 true 為 true，否則有 unknown 就是 unknown；`not(unknown)` 仍是 unknown。只有結構與 budget 全部合法且最終結果為 true 才能選邊。這可避免缺少 State Cell、actor provenance 或錯誤型別被 `not` 反轉成授權成功。Runtime 會重新檢查整棵 package expression；畸形分支不能藏在另一個已為 true 的 `any` 分支後面。

### 1.2 Bounded hierarchy

`parent_by_state` 只記錄 direct child → direct parent；沒有項目的 state 是 root。每個實際有 child 的 compound state 都必須在 `initial_child_by_state` 指定唯一 direct initial child。Compiler 拒絕 cycle、未知 state、非 direct initial child、缺少 initial child，以及超過 16 層的 hierarchy。

Runtime Package 同時保留 authored `initial_state` 與解析後的 `initial_leaf`。StateStore 只儲存 `initial_leaf`／目前 active leaf，祖先路徑由 package hierarchy 推導；因此 Snapshot、EventLog 與 Replay 沒有第二份 active-state 真實來源。`completed`、`failed` 必須是 root leaf，避免 compound terminal 的語義歧義。

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
- hierarchy 是最多 16 層的 acyclic rooted forest，每個 compound state 都有唯一 direct initial child；
- `initial_state` 與每個 transition target 都可確定解析成 active leaf；
- target leaf 不得位於 source state 自己的 subtree；compound 內部切換必須從明確 leaf authoring，避免同一條 ancestor edge 對部分 child 變成 no-op；
- 所有狀態都位於從初始 active leaf 可達的 leaf／ancestor path；
- `completed`／`failed` 不可再有 outgoing transition；
- `on` 必須在共用 EventIR trigger 白名單內；
- `event_match` 最多 16 個有限 JSON scalar，欄位必須屬於該 EventIR 的 payload 契約；
- v0.2–v0.5 `when` 保留最多 16 個條件的 AND list；v0.6 使用 bounded condition expression；所有版本的 `condition_id` 都在同一台機器內唯一，subject／namespace／operator 必須在白名單內；
- v0.6 group depth／child／node／leaf 超限、空 `any`、多 operator、未知 group 或 list 形狀都 fail closed；
- v0.3–v0.6 每條 transition 必須且只能宣告 `on` 或 `after_ticks`；timer tick 必須是 bounded positive integer，timer source 必須是 leaf，且不得搭配 `event_match` 或 actor condition；
- v0.4–v0.6 的 `on: fsm.transitioned` 必須在 `event_match` 同時指定來源 `state_machine_id` 與 `transition_id`；來源必須存在，若另寫 title／owner／authored from／authored to／resolved to leaf／trigger，也必須一致；
- `fsm.transitioned` 機器依賴必須是 DAG，不得 self-loop／cross-loop，最長依賴鏈不得超過 64；v0.1–v0.3 不能偷用這個非終態入口；
- 非等值 operator 的 `value` 必須是有限 number，不能是 boolean；
- `priority` 介於 0 與 1,000,000；同一 `from/on/priority` 或 `from/timer/priority` 不得有歧義（timer 即使 delay 不同，elapsed 後仍可能重疊）；
- manifest 必須明確啟用 `state_machine.core`。

未知欄位一律拒絕。因此 `guard`、`requirements`、`effects`、`reward`、任意 StateStore path 與 Python expression 都不會被悄悄執行。v0.1 來源若偷偷加入 `when`，或 v0.1／v0.2 來源加入 `after_ticks`，都會被拒絕；作者必須明確升級格式與 manifest schema ID。

Compiler 成功不會被視為日後載入的永久信任。`WorldRuntime.from_package()` 會在建立 EntityRegistry、StateStore 或事件訂閱之前，再次檢查 Runtime Package 的必要區段、正式 `schema_contracts`、來源 checksum 記錄，以及 compiled StateIR 的 owner 引用、module authority、hierarchy、initial leaf、transition trigger、condition expression、所有 budget、狀態可達性與跨機器 reaction DAG。外部檔案若缺少 provenance、使用未知文字規則欄位或與已編譯契約不一致，整個 package 會在進入 Runtime 前被拒絕；Runtime 不會把缺少 `when` 解讀成無條件成立。

## 3. Runtime 選邊與提交

收到 EventIR `E` 時，每台 StateIR 以目前 active leaf `Q` 選取符合下列條件的 transition：

```text
transition.from in lineage(Q)  # leaf 本身或任一 ancestor
transition.on == E.event_type
event_match(transition, E.payload) == true
condition_expression(transition.when, StateStore, owner, verified_actor) == true
```

Runtime 先完成 EventIR、payload 與全部條件篩選，再選最高 `priority`；若同 priority 的 leaf 與 ancestor transition 都符合，較深的 source state 勝出。完全同深度的歧義 fail closed。高優先邊條件失敗時，仍可由較低優先的明確 fallback 接手。

Timer transition 使用同一個 Kernel scheduler tick，沒有第二套時鐘：

```text
eligible_tick = entered_tick + after_ticks
current_tick >= eligible_tick
AND(owner_condition_expression) == true
```

條件尚未成立時，timer 保持 eligible，而不是遺失、忙等或偷偷改寫狀態；條件之後成立時，再由所有 eligible candidate 中的最高 `priority` 唯一選邊。每個 tick 的固定順序是 Action checkpoint 提交與事件反應、StateIR timer batch、到期 Action terminal execution。所有同 tick timer 先從同一份 pre-commit StateStore 選邊，再以 owner／machine ID 排序成一筆 bounded StateDelta／EventIR batch。

條件讀取沒有型別轉換。缺少 actor provenance、缺少 State Cell、非有限數字或錯誤型別回傳 unknown；未知 subject／namespace／operator 或畸形結構使整棵 expression 無效。最終只有 true 通過，因此 unknown 仍 fail closed，且 `not(unknown)` 不會變成 true。Runtime 不發出帶有實際秘密值的診斷 EventIR；條件本身不寫入 StateStore，不消耗隨機數，也不因 UI 讀取而重算世界狀態。

事件型與 timer 型 transition 唯一允許的 effect 是自己的狀態 Cell；有 timer 的機器會在同一交易更新保留 entry-tick Cell：

```text
target_leaf = resolve_initial_child_chain(transition.to)
StateDelta(owner_id, "fsm", state_machine_id, "set", target_leaf)
StateDelta(owner_id, "fsm_runtime", state_machine_id, "set", current_tick)  # timer machine only
```

`state_machine.core` 沒有 ActionIR verb，不能被玩家或 AI 當作直接寫入入口。狀態變更一律經 `WorldRuntime.commit_reaction()`；事件轉移成功後依序保留 `state.committed` 與 `fsm.transitioned`，timer 轉移則依序保留 `state.committed`、`fsm.timer_elapsed` 與 `fsm.transitioned`。Lifecycle payload 的 `from`／`to` 保留 authored transition，`from_leaf`／`to_leaf` 記錄實際狀態變更；進入 root leaf `completed` 或 `failed` 時再發出對應 terminal EventIR。

## 4. 跨層事件與 causation

不同 scope 不直接修改彼此狀態，只能透過 EventIR 串接。例如 Gray Crown 範例同時保留 terminal chain，並新增非終態 chain：

```text
ActionIR(unlock)
  -> door.unlocked
  -> System fsm.transitioned(authored nominal -> incident, active nominal -> breached)
  -> Region fsm.transitioned(watchful -> alerted)
```

每個 reaction EventIR 的 `causation_id` 指向直接觸發它的前一個 EventIR，`correlation_id` 保留整條行為鏈。當 FSM 觸發需要 actor condition 的後續 StateIR，或 terminal FSM 觸發 actor quest 時，Runtime 會沿用 v0.4 的最長 64-edge 依賴界線做有界 EventLog 回溯，找回原始 ActionIR actor；循環、缺失或無法驗證的 provenance 會停止，不會猜測玩家。

Timer 沒有外部 cause。`fsm.timer_elapsed` 以自己的 event ID 建立 correlation root，payload 明確記錄 `after_ticks`、`entered_tick`、`eligible_at_tick` 與 `fired_at_tick`；後續 `fsm.transitioned`／terminal event 的 `causation_id` 指向該 timer event。Replay 會驗證 timer payload 與已編譯 transition 一致。

owner scope 目前只決定狀態所有權與可見性，不是自動事件路由。Runtime 不會因為 `scene: room.vault` 就暗自判定某事件屬於該房間；authoring 必須用正式事件型別與 `event_match` 明確指定。這保留了可重播性，也避免目前尚未標準化的 location payload 被猜測成規則。

EventBus 以同步 FIFO 派送同一筆已提交 EventIR batch；callback 產生的新 EventIR 排到已存在事件後方，不遞迴插隊。每個 root cascade 預設最多派送 4096 個 EventIR。超限時 Runtime 清空尚未派送佇列，將 `runtime.reaction_halted` 直接寫入 EventLog 作為 audit-only 邊界，而且刻意不再發布這個停止事件，避免診斷本身形成新迴圈。已提交的 StateDelta／EventIR 不會被假裝回滾；Replay 會驗證停止 payload 並還原 halt diagnostics。

## 5. 可見性

StateIR 的 authoring visibility 會保守映射到 EventIR：

| StateIR visibility | EventIR visibility |
|---|---|
| `public`、`observable` | `public` |
| entity-owned `private` | `private`，target 為該 entity |
| 非 entity `private`、`inferred`、`system_only` | `audit` |

這個映射不會把推論、秘密或系統內部狀態公開。更細緻的每 actor belief／secret projection 仍需獨立契約。

## 6. Snapshot、Replay 與 Studio

- Compiler 在 Runtime Package 保留 authored `initial_state` 與 resolved `initial_leaf`，StateStore seed 只寫入 leaf。
- Snapshot 保存每一個 scoped `fsm` active-leaf cell 與版本；ancestor path 由 package 推導。
- Snapshot v0.6 透過既有 StateStore 一併保存 `fsm_runtime` entry tick，因此不需要新增 Snapshot 格式或第二份 timer queue。
- Snapshot v0.6 的頂層 `tick` 與 `scheduler.tick` 是同一時鐘的重複一致性欄位；兩者不一致時，loader 在替換任何 live Runtime 結構前拒絕整份 Snapshot。
- EventLog 保存 reaction 的 `state.committed` 與 `fsm.*` EventIR；append 會在寫入記憶體或檔案前拒絕既有 ID、同批重複 ID 與無效事件，並以 Kernel transaction failure 讓 reaction、排程建立／取消等外層交易走同一條原子回滾路徑，確保世界狀態與剛寫出的 log 一致且可重載。
- Replay 使用已提交 Delta 還原結果，不重新抽樣或重跑自由文字；Runtime clock 由完整有序 EventLog 的非負 `timestamp_tick` 還原，不再只依賴 Action lifecycle 事件，因此非零 tick 的一般事件與後續 timer 仍維持決定性。
- `package_overview()` 提供 hierarchy、initial path、機器、owner、states、transitions 與 diagnostics。
- Studio transition projection 會顯示 source path、authored target、resolved target leaf、trigger kind、`on`／`after_ticks` 與完整 authored `when` 定義，供人工審查；它仍是唯讀投影。
- `runtime_overview()` 額外提供每台機器的 `current_state`、`current_path`、`state_version`、`entered_tick` 與目前 leaf 的 pending timer／剩餘 tick。

Studio 投影仍是唯讀；正式修改必須回到 authoring source、Compiler、review 與部署流程，AI 不能直接寫 StateStore。

## 7. v0.6 明確不包含

- 本 StateIR 契約內的 Action-scope 狀態；可中斷／取消、compile-time static phase DAG、sticky priority route、單一路徑 merge、非遞迴 primitive child sequence、bounded phase gates 與 fixed-interval retry/deadline 已由獨立 `action-behaviors/v0.7` 契約提供，但 dynamic／recursive／nested Action Graph、resume／補償／平行子步驟與同步 join 仍未包含；
- parallel region、history state、任意 entry／exit effect，以及 runtime 動態改寫 hierarchy；
- ancestor-authored internal reset；compound 內部切換必須明確指定 source leaf；
- 牆鐘、日曆、多速率 clock、cron、背景 thread、週期 timer、timer cancellation 與玩家／MCP 直接控制權威時間；
- 超出 bounded `all`／`any`／`not` 的自由布林運算、自由形式 guard、腳本、任意 effect/reward；
- Runtime 對 Studio bounded random metadata 的自行抽樣；
- 隱式地理事件路由；
- 自由回饋環、執行期動態新增依賴，或把 cascade budget 當成正常流程分支；
- AI 自動採納草稿或直接改寫 Runtime State。

驗證基線由 `tests/test_scoped_state_machine.py` 覆蓋五種 owner、compound target／initial entry、leaf-over-ancestor specificity、terminal 與 non-terminal 跨層 chaining、terminal FSM 到 Quest、可信 module source、hierarchy／reaction cycle 與 depth rejection、owner／verified actor leaf、`all`／`any`／`not` 三值語義、精確 node／leaf 上限、結構與 budget fail-closed、authoring→Compiler→Package→Runtime／Studio→Snapshot／Replay round-trip、Runtime Package 重載拒絕、event／timer priority、v0.1–v0.5 來源相容、Snapshot、Replay lifecycle／leaf／timer validation、Studio expression／path／countdown projection、legacy seed 相容與 reaction rollback；`tests/test_event_bus.py`、`tests/test_mcp_runtime_bindings.py` 與 `tests/test_runtime.py` 另覆蓋 batch FIFO、EventLog append-time ID 唯一性、Snapshot 雙 tick 一致性、非零 tick Replay、非遞迴有界停止、audit event 與 Replay lifecycle 驗證。最新完整測試數以 `docs/RUNTIME_CAPABILITY_MATRIX.md` 的驗證列為準。
