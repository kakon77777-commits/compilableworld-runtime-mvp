# Action-scope 複合行為執行契約 v0.6

本文件描述 CompilableWorld Runtime 已落地的長時間玩家行為。v0.6 在固定順序、精確 tick、fail-closed phase-entry conditions、bounded retry/deadline 與非遞迴 primitive child Action 上，增加有界 conditional child branch 與固定線性 rejoin；它仍不是任意 Action Graph、自由 expression、parallel/join 或 effect 腳本。

## 1. Authoring 契約

新來源檔使用 `compilableworld.action-behaviors/v0.6`，由 `schemas/action-behaviors.v0.6.schema.json` 約束。每個 behavior 必須宣告：

- `behavior_id`、`title`、唯一 `verb`；
- `phases`：2–64 個固定順序 phase；每個 phase 有唯一 `phase_id`、`title`、1–1,000,000 `duration_ticks`、`when`、nullable `retry` 與 `branches`，原始總長不得超過 1,000,000 tick；
- final phase 的 `branches` 必須為空。其他 phase 可為空，或宣告 2–16 個 priority branch；整個 v0.6 behavior 至少有一組 branch，而且至少一個 branch 含 primitive child Action；
- `completion_module`：manifest 明確啟用的 Runtime Module；啟動後 Kernel 會再確認實際 verb owner 與這個宣告一致；
- `concurrency: one_per_actor`；
- `interrupt_on`：最多 16 個不重複的 bounded EventIR。

中斷仍只接受 `movement.actor_moved`、`combat.damage_applied`、`combat.actor_defeated`。未知欄位、重複 verb／phase／condition、未知 module、自由 guard、腳本、任意 StateStore path 或通用 effect 一律在編譯期拒絕。

舊 `compilableworld.action-behaviors/v0.1` 單階段、v0.2 sequential、v0.3 condition-gated、v0.4 retry-bounded 與 v0.5 direct-child 來源仍可編譯；Compiler 會保留實際 `source_schemas.action_behaviors`，同時把 package 的最新正式契約標成 v0.6。它不會替舊來源假造不存在的 phases、conditions、retry policy、child step 或 branch。

## 2. Runtime lifecycle

玩家提交已 authored 的 verb 時，Kernel 以 authoring duration 為準。若 ActionIR 另帶不相符的 delay，或同一 actor 已有 authored 行為，提交會 fail closed。正常完成順序是：

```text
ActionIR
  -> action.scheduled
  -> Scheduler 逐 tick 推進
  -> select(completed_phase.branches by priority once)
       -> action.branch_selected
  -> execute(selected_branch.child_action once)
       -> action.child_started
       -> primitive_module.evaluate(child ActionIR)
       -> state.committed + module EventIR + action.child_completed
       -> action.child_failed + parent action.failed（primitive 拒絕）
  -> evaluate(next_phase.when)
       -> action.retry_scheduled（條件不成立且尚在 authored retry/deadline 內）
       -> action.failed（無 retry，或次數/deadline 已耗盡）
       -> action.progressed（全部成立）
  -> 最終 tick 到期
  -> action.started
  -> completion_module.evaluate(ActionIR)
  -> StateStore.commit(StateDelta)
  -> state.committed
  -> module EventIR
  -> action.completed
```

`action.scheduled` 含 private、可重建的 ActionIR；其他 lifecycle payload 只暴露有界識別與結果。完成模組仍遵守普通 Module Contract：只能回傳 StateDelta／EventIR，不能直接寫 StateStore。

`action.branch_selected` 固定包含 behavior／phase／branch ID、唯一 priority、下一個線性 phase 與 nullable child step ID。`action.progressed` 固定包含已完成 phase、下一 phase、1-based phase index、已完成／總 phase 數、累積／總 tick。`advance(N)` 內部逐 tick 解算，所以跨越多個 tick 也不會漏掉中途 checkpoint；EventLog append 失敗時會把該 tick、branch choice 與 child 結果一起回滾，下一次只重試一次。兩種事件與 child lifecycle 都可驅動 Quest／scoped StateIR，但沒有 generic StateDelta 或自由 effect 入口。

如果完成模組拒絕行為或提交失敗，Runtime 產生 `action.failed`，不會留下部分 StateDelta。生命週期事件和完成結果共用既有 EventLog／EventBus 因果鏈，因此 Quest 或 scoped StateIR 可以監聽白名單內的 `action.*` EventIR。

## 3. Bounded conditional child branch

每組非空 `branches` 必須有 2–16 個選項。每個 branch 固定包含全 behavior 唯一的 `branch_id`、0–1,000,000 唯一 `priority`、最多 16 個既有 bounded AND conditions，以及 nullable `child_action`。一組中必須恰有一個 `when: []` 的 fallback；fallback priority 必須低於所有 conditional branch。Compiler 依 priority 由高至低正規化，Kernel 選第一個全部條件成立的 branch，因此不依 JSON 輸入順序猜測，也不會沒有 fallback。

選擇只在該 phase boundary 第一次抵達時進行，並寫入 pending Action 的 `selected_branches[phase_id]`。若下一 phase gate 失敗而 retry，Kernel 重用原 branch，不重新讀 StateStore 來改選；成功 child 也不重跑。branch 執行後只能回到原本下一個線性 phase，這是 implicit join，不是任意 `next_phase_id` 路由。EventLog 與 Snapshot 都保存選擇，Replay 會驗證 branch ID、priority、next phase 與 child step 是否符合編譯後契約。

branch conditions 使用第 4 節同一套 subject／namespace／operator／finite scalar 契約；沒有 OR、NOT、自由 guard 或 AI 裁決。編譯後 branch 集合損壞、選擇不存在或無法解析時，父 Action 以 `failure_code: branch_unresolved` fail closed。

## 4. Bounded primitive child Action

每個被選中的 branch 最多有一個固定 child step；所有非 null step 依 phase／已選 branch 順序形成實際 sequence。v0.5 相容來源則保留每個非 final phase 的 direct child。child 固定繼承父 Action 的 actor 與 correlation，由 Kernel 建立 `authority: runtime` 的新 ActionIR；作者不能指定 child actor、authority、delay 或另一個 authored behavior。可用 verb 僅限目前內建 primitive 白名單：`look`、`move`、`open`、`unlock`、`take`、`drop`、`give`、`inventory`、`status`、`attack`、`cast`、`say`、`talk`、`quests`。

每個 child 固定包含：

- 全 behavior 唯一的 `step_id`；
- 白名單 `verb`，Compiler 同時固化並驗證唯一 `module_id`；
- nullable target；需要 target 的 verb 只能引用父 Action target 或一個編譯期已知 entity，無 target verb 禁止偷帶 target；
- 每個 verb 各自的 args 白名單與必填欄位，例如 `move.direction`、`cast.spell`、`say.text`、`give.recipient`；最多 16 個 finite scalar，recipient 也必須是編譯期已知 entity。

在 phase boundary，Kernel 先固定 branch，再執行尚未完成的 selected child，最後以 child StateDelta 提交後的直接 StateStore 評估下一 phase gate。child Module 只能回傳自己的 StateDelta／EventIR；Kernel 將 `action.branch_selected`、`action.child_started`、`state.committed`、module EventIR、`action.child_completed` 與同一 boundary 的父 progress／retry／failure寫入同一 EventLog batch。append 失敗會一起回滾 StateStore、tick、queue、ActionStatus、child registry、retry、`selected_branches` 與 `completed_steps`。

child 拒絕或提交錯誤會產生 `action.child_failed`，父 Action 以 `failure_code: child_action_failed` 終止。契約刻意沒有 compensation：先前 tick 已成功提交的 child step 仍是正式世界歷史，不會因後續 step 失敗而暗中撤銷。由同一父 correlation 產生的 child 移動／戰鬥事件不會反過來中斷自己的父 Action，但仍可正常驅動其他 EventIR listener。

## 5. Bounded phase condition

第一個 phase 的 `when` 必須是空陣列；後續每個 phase 最多 16 個條件，以 AND 語義在進入該 phase 前判定。若上一 phase 有 child，條件讀取該 child 直接 StateDelta 已提交後的 StateStore；同 tick 多個排程項目依 Scheduler 穩定順序解算，不等待 EventBus subscriber 的後續 reaction。每條條件固定包含：

- 唯一 `condition_id`；
- `subject: actor | target`；target 不存在或不是已知 entity 時失敗；
- 白名單 namespace：`combat`、`door`、`exploration`、`fsm`、`health`、`inventory`、`magic`、`position`、`quest`、`status`、`wallet`；
- 明確 `key`；
- `equals`、`not_equals` 或四種數值大小比較；
- finite JSON scalar `value`。

缺失 State Cell、非有限數字、錯誤型別與未知 subject／namespace／operator 都不會被轉型或猜測，結果一律 false；boolean 與 `0/1` 不視為相等。任一條件失敗時，Kernel 只公開 phase／condition ID 與 bounded reason，不公開實際 State Cell 值；沒有 retry policy 時原子寫入 `action.failed` 並移除排程，有 policy 時改走下一節的 bounded retry。這些事件都可以被 Quest／scoped StateIR 監聽。

## 6. Bounded retry 與 timeout

只有非首 phase、而且 `when` 至少有一條條件時，`retry` 才能是物件。它固定包含：

- `max_attempts`：1–16，代表初次 gate 失敗後最多可排入幾次 retry；
- `interval_ticks`：1–1,000,000，每次固定延後幾個 authoritative tick；
- `timeout_ticks`：1–1,000,000，從第一次 gate 失敗起算的 deadline。

失敗時，Kernel 以 `attempt <= max_attempts` 且 `retry_at_tick <= timeout_at_tick` 共同判斷。成立便原子延後原 Action 的 final due tick、保存 phase attempt/deadline，並發出 private `action.retry_scheduled`；不成立才以 `failure_code: retry_exhausted` 發出 terminal `action.failed`。因此 `max_attempts: 2` 最多會看見兩個 retry event，若第三次 gate evaluation 仍失敗，第三次是 terminal failure 而不是第三次 retry。

retry EventIR 包含 attempt、固定 interval、first failure tick、next retry tick、deadline 與更新後 due tick，可被 StateIR equality mapping 使用。EventLog append 失敗時，tick、queue、due tick、ActionStatus 與 retry state 一起回滾；不會消耗一次隱形 attempt。

本契約沒有 exponential backoff、自由公式、random jitter、AI 自行延長 deadline 或無限 retry。等待期間條件若恢復，下一個 authored retry tick 會正常產生 `action.progressed`，再依剩餘 phase duration 完成原 Action。

## 7. 取消與事件中斷

- `cancel_action(actor_id, action_id)` 只允許排程所有者取消，成功後產生 `action.cancelled`。
- 只有 `EventIR.target` 等於排程 actor，而且事件型別出現在該 behavior 的 `interrupt_on` 時，才會產生 `action.interrupted`。
- 移動、受傷、被擊敗都必須先是 Runtime 已提交的正式 EventIR；UI、AI 或自由文字不能偽造內部中斷判定。
- 取消或中斷會將項目與 retry／branch／child progress 從 Scheduler／Runtime 移除。v0.6 不保留 resumable continuation，也不執行補償 effect。

若 `action.scheduled`、`action.cancelled` 或 `action.interrupted` 寫入 EventLog 失敗，Kernel 會回復 queue 與 action registry，避免「事件說沒排程但 queue 有工作」或反向的半完成狀態。

## 8. Gray Crown 垂直切片

`behavior.search.careful` 將 `search` 定義為「觀察搜索範圍」與「仔細檢查線索」兩個各一 tick 的 phase。第一個 phase 依 `survey_actor_alive` 選擇 `survey.alive`（priority 100，執行 `survey.room`／`look`）或 `survey.fallback`（priority 0，執行 `survey.status`／`status`），再共同 rejoin 到 `inspect`。第二 phase 的 `actor_alive` 不成立時最多以一 tick間隔 retry 兩次；即使期間 alive 改變，已選 branch 與已完成 child 都不重選、不重跑。持續失敗則在 deadline 發出 `action.failed(failure_code=retry_exhausted)`。通過 gate 後的下一個 final due tick 才由 `exploration.core` 提交：

```text
StateDelta(<actor>, exploration, search_count, increment)
EventIR(exploration.searched, target=<actor>)
```

終端會即時顯示 branch、child、phase checkpoint 與 retry 次數／next tick；`pending` 顯示 action ID、behavior、目前 phase、安全 branch ID／priority／condition IDs、child step ID／完成數、retry policy、attempt、next retry、deadline 與目前／總 tick，但不公開 child args 或條件 path／operator／value。`cancel <action_id>` 只能取消目前 actor 自己的行為。外部移動或正常戰鬥傷害會在事件提交後中斷尚未完成的搜索。

## 9. Snapshot、Replay 與投影

- Snapshot v0.5 保存目前 tick、排程 ActionIR、due tick、每個 pending Action 的 attempt／first failure／next retry／deadline、必須符合 authored path 的 `selected_branches` 與 `completed_steps`；v0.1–v0.4 仍有明確 migration，舊版 branch progress 以空物件開始。
- EventLog Replay 套用所有已提交 `state.committed`，並以 private `action.scheduled`、`action.branch_selected`、`action.child_completed`、`action.retry_scheduled`、`action.progressed` 與 terminal lifecycle 事件重建 pending queue、更新 due tick、branch、retry 與 child progress。
- 純 EventLog 不記錄 checkpoint 之間沒有產生事件的靜默 tick，因此 Replay 不猜測其流逝；需要 checkpoint 之間的精確進度時使用 Snapshot。
- Studio `package_overview()` 顯示完整 behavior／phase／branch／child／condition／retry 定義與 diagnostics；player/runtime pending projection只顯示 branch ID／priority／condition IDs、child step ID／完成數，以及安全的 retry policy／attempt／next tick／deadline，不顯示 child args、State Cell path、operator 或 value。
- MCP Action Gateway 將 `scheduled` 視為已接受、可稽核與可 idempotent replay 的 receipt，而不是失敗；世界狀態是否已改變仍要等 completion commit。

Runtime host 仍擁有時間推進權。v0.6 沒有提供讓玩家或 MCP 任意前進 authoritative tick 的遠端工具；本機終端的 `tick` 是 operator/debug 入口。

## 10. 明確邊界

本契約尚未包含：

- pause／resume、checkpoint continuation 或補償交易；
- 任意 phase routing／child Action graph、遞迴 authored behavior、動態 actor／authority／target、自由 effects 或直接 StateDelta；
- nested branching、OR／NOT condition graph、parallel、顯式 join、loop 或 history state；
- exponential/free-form backoff、random jitter、無限 retry 或動態 deadline extension；
- 任意 guard、腳本、公式式中斷或 Runtime random sampling；
- generic effect DSL 或跨模組直接呼叫；
- Studio 視覺化 behavior authoring／直接 write-back；
- AI 直接寫 StateStore 或自行提交不可逆效果。

驗證基線由 `tests/test_action_behavior.py` 覆蓋 v0.6 編譯、v0.1–v0.5 相容、priority／fallback／condition／child fail-closed 驗證、sticky branch selection、implicit rejoin、primitive whitelist／target／args／module／禁止遞迴、child lifecycle／StateDelta／failure／不重跑、retry recovery／exhaustion、Snapshot v0.5／v0.1–v0.4 migration、Replay tamper rejection、完整 transaction rollback、Studio redaction，以及 branch／child／progress／retry／failure／completion EventIR 驅動 scoped StateIR；MCP scheduled receipt 另有整合測試。完整測試為 310/310。
