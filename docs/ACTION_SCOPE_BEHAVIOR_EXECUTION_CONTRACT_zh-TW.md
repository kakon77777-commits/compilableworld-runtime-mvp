# Action-scope 複合行為執行契約 v0.2

本文件描述 CompilableWorld Runtime 已落地的長時間玩家行為。v0.2 在既有可取消、可中斷、可快照與可重播的 lifecycle 上，增加固定順序、精確 tick 的 phase checkpoints，但仍不把 authoring 變成任意 effect 腳本。

## 1. Authoring 契約

新來源檔使用 `compilableworld.action-behaviors/v0.2`，由 `schemas/action-behaviors.v0.2.schema.json` 約束。每個 behavior 必須宣告：

- `behavior_id`、`title`、唯一 `verb`；
- `phases`：2–64 個固定順序 phase；每個 phase 有唯一 `phase_id`、`title` 與 1–1,000,000 `duration_ticks`，總長不得超過 1,000,000 tick；
- `completion_module`：manifest 明確啟用的 Runtime Module；啟動後 Kernel 會再確認實際 verb owner 與這個宣告一致；
- `concurrency: one_per_actor`；
- `interrupt_on`：最多 16 個不重複的 bounded EventIR。

中斷仍只接受 `movement.actor_moved`、`combat.damage_applied`、`combat.actor_defeated`。未知欄位、重複 verb／phase、未知 module、自由 guard、腳本、任意 StateStore path 或通用 effect 一律在編譯期拒絕。

舊 `compilableworld.action-behaviors/v0.1` 單階段來源仍可編譯；Compiler 會保留其實際 `source_schemas.action_behaviors` 為 v0.1，同時把 package 的最新正式契約標成 v0.2。它不會假造不存在的 phases 或改變舊 lifecycle。

## 2. Runtime lifecycle

玩家提交已 authored 的 verb 時，Kernel 以 authoring duration 為準。若 ActionIR 另帶不相符的 delay，或同一 actor 已有 authored 行為，提交會 fail closed。正常完成順序是：

```text
ActionIR
  -> action.scheduled
  -> Scheduler 逐 tick 推進
  -> action.progressed（每個非最終 phase 邊界）
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

## 3. 取消與事件中斷

- `cancel_action(actor_id, action_id)` 只允許排程所有者取消，成功後產生 `action.cancelled`。
- 只有 `EventIR.target` 等於排程 actor，而且事件型別出現在該 behavior 的 `interrupt_on` 時，才會產生 `action.interrupted`。
- 移動、受傷、被擊敗都必須先是 Runtime 已提交的正式 EventIR；UI、AI 或自由文字不能偽造內部中斷判定。
- 取消或中斷會將項目從 Scheduler 移除。v0.2 不保留 resumable continuation，也不執行補償 effect。

若 `action.scheduled`、`action.cancelled` 或 `action.interrupted` 寫入 EventLog 失敗，Kernel 會回復 queue 與 action registry，避免「事件說沒排程但 queue 有工作」或反向的半完成狀態。

## 4. Gray Crown 垂直切片

`behavior.search.careful` 將 `search` 定義為「觀察搜索範圍」與「仔細檢查線索」兩個各一 tick 的 phase。第一 tick 發出 `action.progressed(phase_id=survey, next_phase_id=inspect)`；第二 tick 才由 `exploration.core` 提交：

```text
StateDelta(<actor>, exploration, search_count, increment)
EventIR(exploration.searched, target=<actor>)
```

終端會即時顯示 phase checkpoint；`pending` 顯示 action ID、behavior、目前 phase、已完成 phase 數與目前／總 tick，`cancel <action_id>` 只能取消目前 actor 自己的行為。移動或正常戰鬥傷害會在事件提交後中斷尚未完成的搜索。

## 5. Snapshot、Replay 與投影

- Snapshot 保存目前 tick、排程 ActionIR、due tick 與 lifecycle registry，可精確恢復 progress。
- EventLog Replay 套用所有已提交 `state.committed`，並以 private `action.scheduled` 減去 terminal lifecycle 事件重建 pending queue；`action.progressed` 可把重播 tick 推進到最後一個正式 checkpoint。
- 純 EventLog 不記錄 checkpoint 之間沒有產生事件的靜默 tick，因此 Replay 不猜測其流逝；需要 checkpoint 之間的精確進度時使用 Snapshot。
- Studio `package_overview()` 顯示 behavior／phase 定義與 diagnostics；`runtime_overview()` 額外顯示 pending action 的 current phase 與 progress。
- MCP Action Gateway 將 `scheduled` 視為已接受、可稽核與可 idempotent replay 的 receipt，而不是失敗；世界狀態是否已改變仍要等 completion commit。

Runtime host 仍擁有時間推進權。v0.2 沒有提供讓玩家或 MCP 任意前進 authoritative tick 的遠端工具；本機終端的 `tick` 是 operator/debug 入口。

## 6. 明確邊界

本契約尚未包含：

- pause／resume、checkpoint continuation 或補償交易；
- 會逐 phase 執行任意 primitive Action／StateDelta 的 child Action Graph；
- conditional、retry、timeout、parallel、join 或 history state；
- 任意 guard、腳本、公式式中斷或 Runtime random sampling；
- generic effect DSL 或跨模組直接呼叫；
- Studio 視覺化 behavior authoring／直接 write-back；
- AI 直接寫 StateStore 或自行提交不可逆效果。

驗證基線由 `tests/test_action_behavior.py` 覆蓋 v0.2 編譯與 v0.1 相容、精確 tick checkpoints、完成、取消、移動／傷害中斷、並行限制、Snapshot、completed 與 pending Replay、schedule／cancel／progress EventLog rollback、失敗完成、Studio、Parser，以及 `action.progressed`／`action.completed` 驅動 scoped StateIR；MCP scheduled receipt 另有整合測試。完整測試為 285/285。
