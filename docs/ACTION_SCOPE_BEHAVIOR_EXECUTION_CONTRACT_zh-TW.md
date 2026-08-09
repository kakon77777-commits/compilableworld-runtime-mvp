# Action-scope 複合行為執行契約 v0.3

本文件描述 CompilableWorld Runtime 已落地的長時間玩家行為。v0.3 在固定順序、精確 tick 的 phase checkpoints 上增加 fail-closed phase-entry conditions，但仍不把 authoring 變成任意 expression 或 effect 腳本。

## 1. Authoring 契約

新來源檔使用 `compilableworld.action-behaviors/v0.3`，由 `schemas/action-behaviors.v0.3.schema.json` 約束。每個 behavior 必須宣告：

- `behavior_id`、`title`、唯一 `verb`；
- `phases`：2–64 個固定順序 phase；每個 phase 有唯一 `phase_id`、`title`、1–1,000,000 `duration_ticks` 與 `when`，總長不得超過 1,000,000 tick；
- `completion_module`：manifest 明確啟用的 Runtime Module；啟動後 Kernel 會再確認實際 verb owner 與這個宣告一致；
- `concurrency: one_per_actor`；
- `interrupt_on`：最多 16 個不重複的 bounded EventIR。

中斷仍只接受 `movement.actor_moved`、`combat.damage_applied`、`combat.actor_defeated`。未知欄位、重複 verb／phase／condition、未知 module、自由 guard、腳本、任意 StateStore path 或通用 effect 一律在編譯期拒絕。

舊 `compilableworld.action-behaviors/v0.1` 單階段與 v0.2 sequential 來源仍可編譯；Compiler 會保留實際 `source_schemas.action_behaviors`，同時把 package 的最新正式契約標成 v0.3。它不會替舊來源假造不存在的 phases 或 conditions。

## 2. Runtime lifecycle

玩家提交已 authored 的 verb 時，Kernel 以 authoring duration 為準。若 ActionIR 另帶不相符的 delay，或同一 actor 已有 authored 行為，提交會 fail closed。正常完成順序是：

```text
ActionIR
  -> action.scheduled
  -> Scheduler 逐 tick 推進
  -> evaluate(next_phase.when)
       -> action.failed（任一條件不成立）
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

`action.progressed` 固定包含已完成 phase、下一 phase、1-based phase index、已完成／總 phase 數、累積／總 tick。`advance(N)` 內部逐 tick 解算，所以跨越多個 tick 也不會漏掉中途 checkpoint；EventLog append 失敗時會把該 tick 回滾，下一次只重試一次。這個事件可驅動 Quest／scoped StateIR，但 checkpoint 本身沒有 generic StateDelta 或 child Action effect。

如果完成模組拒絕行為或提交失敗，Runtime 產生 `action.failed`，不會留下部分 StateDelta。生命週期事件和完成結果共用既有 EventLog／EventBus 因果鏈，因此 Quest 或 scoped StateIR 可以監聽白名單內的 `action.*` EventIR。

## 3. Bounded phase condition

第一個 phase 的 `when` 必須是空陣列；後續每個 phase 最多 16 個條件，以 AND 語義在進入該 phase 前、同一 tick 的共同 StateStore snapshot 上判定。每條條件固定包含：

- 唯一 `condition_id`；
- `subject: actor | target`；target 不存在或不是已知 entity 時失敗；
- 白名單 namespace：`combat`、`door`、`exploration`、`fsm`、`health`、`inventory`、`magic`、`position`、`quest`、`status`、`wallet`；
- 明確 `key`；
- `equals`、`not_equals` 或四種數值大小比較；
- finite JSON scalar `value`。

缺失 State Cell、非有限數字、錯誤型別與未知 subject／namespace／operator 都不會被轉型或猜測，結果一律 false；boolean 與 `0/1` 不視為相等。任一條件失敗時，Kernel 原子寫入 private `action.failed`，payload 只包含 phase／condition ID 與 bounded reason，不公開實際 State Cell 值，並移除排程。這個事件可以被 Quest／scoped StateIR 監聽。

## 4. 取消與事件中斷

- `cancel_action(actor_id, action_id)` 只允許排程所有者取消，成功後產生 `action.cancelled`。
- 只有 `EventIR.target` 等於排程 actor，而且事件型別出現在該 behavior 的 `interrupt_on` 時，才會產生 `action.interrupted`。
- 移動、受傷、被擊敗都必須先是 Runtime 已提交的正式 EventIR；UI、AI 或自由文字不能偽造內部中斷判定。
- 取消或中斷會將項目從 Scheduler 移除。v0.3 不保留 resumable continuation，也不執行補償 effect。

若 `action.scheduled`、`action.cancelled` 或 `action.interrupted` 寫入 EventLog 失敗，Kernel 會回復 queue 與 action registry，避免「事件說沒排程但 queue 有工作」或反向的半完成狀態。

## 5. Gray Crown 垂直切片

`behavior.search.careful` 將 `search` 定義為「觀察搜索範圍」與「仔細檢查線索」兩個各一 tick 的 phase。進入第二 phase 前必須通過 `actor_alive`；成立時第一 tick 發出 `action.progressed(phase_id=survey, next_phase_id=inspect)`，不成立則發出 `action.failed(phase_id=inspect, condition_id=actor_alive)`。第二 tick 才由 `exploration.core` 提交：

```text
StateDelta(<actor>, exploration, search_count, increment)
EventIR(exploration.searched, target=<actor>)
```

終端會即時顯示 phase checkpoint；`pending` 顯示 action ID、behavior、目前 phase、condition IDs、已完成 phase 數與目前／總 tick，但不公開條件 path／operator／value。`cancel <action_id>` 只能取消目前 actor 自己的行為。移動或正常戰鬥傷害會在事件提交後中斷尚未完成的搜索。

## 6. Snapshot、Replay 與投影

- Snapshot 保存目前 tick、排程 ActionIR、due tick 與 lifecycle registry，可精確恢復 progress。
- EventLog Replay 套用所有已提交 `state.committed`，並以 private `action.scheduled` 減去 terminal lifecycle 事件重建 pending queue；`action.progressed` 可把重播 tick 推進到最後一個正式 checkpoint。
- 純 EventLog 不記錄 checkpoint 之間沒有產生事件的靜默 tick，因此 Replay 不猜測其流逝；需要 checkpoint 之間的精確進度時使用 Snapshot。
- Studio `package_overview()` 顯示完整 behavior／phase／condition 定義與 diagnostics；player/runtime pending projection 只顯示 condition IDs、current phase 與 progress。
- MCP Action Gateway 將 `scheduled` 視為已接受、可稽核與可 idempotent replay 的 receipt，而不是失敗；世界狀態是否已改變仍要等 completion commit。

Runtime host 仍擁有時間推進權。v0.3 沒有提供讓玩家或 MCP 任意前進 authoritative tick 的遠端工具；本機終端的 `tick` 是 operator/debug 入口。

## 7. 明確邊界

本契約尚未包含：

- pause／resume、checkpoint continuation 或補償交易；
- 會逐 phase 執行任意 primitive Action／StateDelta 的 child Action Graph；
- if/else branching、OR／NOT condition graph、retry、timeout、parallel、join 或 history state；
- 任意 guard、腳本、公式式中斷或 Runtime random sampling；
- generic effect DSL 或跨模組直接呼叫；
- Studio 視覺化 behavior authoring／直接 write-back；
- AI 直接寫 StateStore 或自行提交不可逆效果。

驗證基線由 `tests/test_action_behavior.py` 覆蓋 v0.3 編譯、v0.1／v0.2 相容、actor／target 與 strict/numeric comparison、精確 tick checkpoints、條件失敗 receipt/EventIR、完成、取消、中斷、Snapshot、Replay、schedule／cancel／progress／condition rollback、Studio redaction，以及 `action.progressed`／conditional `action.failed`／`action.completed` 驅動 scoped StateIR；MCP scheduled receipt 另有整合測試。完整測試為 290/290。
