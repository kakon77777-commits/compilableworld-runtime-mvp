# World State Machine 執行契約 v0.1

本文件描述 CompilableWorld Runtime 目前已實作的世界狀態機計算順序。
它是 Runtime 的執行契約，不是 AI prompt，也不是 EveGlyph 的 UI 規格。

## 1. 核心資料

對一個 actor 與一個 quest/state machine，Runtime 維持：

- `S_t`：tick `t` 的 StateStore snapshot；
- `E_t`：由正常 ActionIR pipeline 產生的 EventIR；
- `Q_t`：該 actor 目前的 state machine state；
- `T`：編譯後、通過 schema 的 transition 集合。

Studio 的 `variables`、`instructions`、`responses` 與 bounded `random` 目前先保留在
World IR／mapping artifact 中。它們不會因為匯入而直接寫進 Runtime State，也不會自動
成為可執行 guard。

Studio transition 可以明確提供 bounded `requirements`。目前只接受
`reach:room_id` 與 `deliver:item_id:target_id`，最多 32 條；World IR、mapping
與 `studio-compile` 會保留同一組條件。mapping 不得刪除或改寫來源 requirements，
而 room／item／target 是否存在則由後續正常 compiler 對 base world 驗證。

可執行 trigger 與可比對 payload 欄位由
`src/compilableworld/state_machine.py` 的單一契約共享給 Studio、Compiler 與 Runtime：

- Kernel Action lifecycle：`action.scheduled`、`action.child_started`、`action.child_completed`、`action.child_failed`、`action.progressed`、`action.retry_scheduled`、`action.started`、`action.completed`、`action.cancelled`、`action.interrupted`、`action.failed`；
- Movement／Inventory／Door：移動、拿取、交付、放下、開門與解鎖事件；
- Dialogue：`dialogue.spoken`、`dialogue.responded`；
- Combat／Magic：miss、damage、defeated 與 `magic.cast`；
- Quest chaining：`quest.completed`、`quest.failed`。
- Exploration：`exploration.searched`。

`state.committed` 與純查詢／觀察事件不在 trigger 白名單內。這避免把讀取 UI 或任意
StateStore path 變成隱含規則。

## 2. Transition selection

一條 transition `τ` 只有在以下條件全部成立時才是候選：

```text
τ.from == Q_t
τ.on == E_t.event_type
event_match(τ, E_t) == true
requirements(τ, S_t, actor) == true
```

其中：

- `event_match` 是 EventIR payload 的純量等值比對；
- Studio adapter 只接受最多 16 個 `event_match` 欄位，並在 mapping 後依目標 EventIR 白名單檢查欄位；
- v0.1 requirements 只有明確的 `deliver:item_id:target_id` 與
  `reach:room_id`；
- 若沒有候選，`Q_t` 不變，也不產生 quest transition；
- 若有多條候選，Runtime 選擇 `priority` 最大者；
- Studio adapter 與 Compiler 都將 `priority` 限定為 0–1,000,000；
- `reward` 只允許 `completed` transition 的 0–1,000,000,000 currency。

```text
τ* = argmax(priority(τ), τ ∈ candidates)
```

編譯器禁止相同 `from/on/priority` 的未解決衝突，並禁止從 `completed` 或 `failed`
再建立 transition；它也拒絕從 `initial_state` 在結構上不可達的 transition source。
所有可執行 EventIR 類型都必須在白名單內，`event_match` 最多 16 個 JSON finite
scalar 欄位，`requirements` 最多 32 條。

Runtime 執行的是已編譯、已正規化的 Runtime Package；例如每條 transition 的
`requirements` 欄位由 compiler 正規化為陣列。Runtime 不會為未編譯或缺欄位的
authoring object 猜測預設值。

## 3. StateDelta 與事件順序

玩家行動的正常流程是：

```text
ActionIR
  → module.evaluate()
  → StateStore.commit(StateDelta)
  → state.committed
  → primary EventIR
  → EventBus subscribers
  → QuestModule transition selection
  → reaction StateDelta commit
  → quest.transitioned
  → quest.completed / quest.failed (若進入終態)
```

因此，一個由對話觸發任務轉移的典型事件順序是：

```text
state.committed
dialogue.responded
state.committed
quest.transitioned
```

如果轉入 `completed`，最後再追加 `quest.completed`；如果轉入 `failed`，則追加
`quest.failed`。每個 reaction 都透過 Kernel 的 `commit_reaction()`，不能由 Dialogue
或 EveGlyph 直接寫入 `quest.*`。

`quest.completed`／`quest.failed` 可以觸發另一個 actor-scoped state machine，形成
可追蹤的任務鏈。因為來源任務已進入 terminal state 且 terminal state 禁止 outgoing
transition，這個 chaining 點不會讓來源任務自行重開或重複領取獎勵。

## 4. 原子性與因果鏈

- 一次 ActionIR 的所有 StateDelta 必須整批通過權限與版本檢查；失敗時回滾。
- EventLog append 失敗時，StateStore 也回滾，不留下半完成狀態。
- reaction 的 `quest.*` 事件以觸發 EventIR 的 `event_id` 作為 `causation_id`。
- Runtime 優先由 `EventIR.causation_id → ActionIR.actor_id` 決定要推進哪個 actor；
  沒有 ActionIR provenance 時才接受明確 payload actor，最後只對具 `quest` component
  的 event target fallback。門或受擊目標不會被誤認成行動者。
- 所有事件帶有 Runtime tick；Snapshot 與 Replay 以 StateStore／EventLog 作為恢復邊界。
- MCP、Studio、Web Gateway 都只能透過這條 pipeline，不得繞過 Kernel 直接改 StateStore。

## 5. Studio 到 Runtime 的步驟

```text
EveGlyph YAML / AI draft
  → local structural validation
  → read-only Runtime import
  → World IR + diagnostics + mapping suggestion
  → human mapping review
  → mapping validation
  → studio-compile on a staged copy of the base world
  → normal compile_world()
  → Runtime Package
```

`studio-compile` 不會修改 base authoring source。未明確映射的 room、EventIR、guard
或 package 語義必須停在 review artifact，不得被猜測成 Runtime 規則。自由文字
`guards` 仍然不可執行；只有通過上述 bounded grammar 的 `requirements` 才能進入
compiled quest transition。

在 Studio 匯入與 mapping validation 階段，同一 `from`／`on`／`priority` 組合不得
重複（即使 target 相同），否則會產生 error，而不是讓 Runtime 以來源順序猜測。World IR
已有任何 validation error 時，mapping report 也必須保持 `mapping_complete: false`；
只有修正來源後，才可進入 reviewed overlay 與 `studio-compile`。

## 6. 目前尚未包含的語義

以下不是本契約已經承諾的功能：

- 自由形式文字 guard 的直接執行；
- Studio bounded random 的 Runtime 狀態抽樣；
- AI 自行決定不可逆世界轉移；
- 跨主機 consensus、分散式 ACID 或多世界 hosting；
- actor belief／secret 的通用投影。

這些需要各自的版本化資料契約、測試與授權邊界，不能由自然語言草稿自動推導。

## 7. 回歸測試對照

`tests/test_world_state_machine.py` 對應本契約的主要保證：

- priority 最大候選勝出；
- event payload match 不符時不轉移；
- `reach` requirement 不滿足時不轉移；
- 事件反應的 state／quest event 順序與 causation；
- door target 與 ActionIR actor 的正確歸屬；
- terminal quest chaining、多玩家隔離與 reward exactly-once；
- Snapshot round-trip、EventLog Replay 與 reaction rollback；
- 編譯器拒絕 terminal outgoing、不可達 branch、衝突與超出上限的值。

Studio 端另由 `tests/test_studio_world_ir.py`、`tests/test_studio_mapping.py`
與 `tests/test_studio_compile.py` 保證 requirements 的 bounded validation、
mapping preservation 與 compiled quest overlay。
