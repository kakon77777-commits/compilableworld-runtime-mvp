# CompilableWorld Runtime MVP v0.1.1

這是一套零第三方執行依賴的 Python 參考實作。CompilableWorld Runtime 將 JSON／CSV Authoring Layer 編譯為 Runtime Package，再由 MSSP 模組化世界核心透過終端機或網頁介面執行——兩者共用同一套 Kernel／Action IR／Module Contract，只是不同的 UI Adapter（見「架構邊界」）。原有 `compilableworld` Python import 與 `cw-runtime` CLI 保持相容。

## 快速開始

不安裝也可直接執行：

```bash
cd compilableworld-runtime-mvp
PYTHONPATH=src python3 -m compilableworld validate examples/gray_crown
PYTHONPATH=src python3 -m compilableworld compile examples/gray_crown --out build/gray_crown
PYTHONPATH=src python3 -m compilableworld play build/gray_crown/world.package.json
```

或以 editable mode 安裝：

```bash
python3 -m pip install -e .
cw-runtime compile examples/gray_crown --out build/gray_crown
cw-runtime play build/gray_crown/world.package.json
```

## 網頁介面

零依賴（純 stdlib `http.server`，沒有 Flask/WebSocket，避免額外供應鏈風險）的可視化介面，與終端機共用同一個 Kernel／Intent Parser：

```bash
PYTHONPATH=src python3 -m compilableworld serve build/mingyun_zhiyu_peace_city/world.package.json --port 8765
```

開啟 `http://127.0.0.1:8765/`，可看到房間場景、可點擊的出口（含門鎖狀態）、物品拾取／放下／交付按鈕（交付對象下拉選單只列出場景內的角色/生物，不含門或其他非生命實體）、角色的「交談」按鈕、生命值條、貨幣、任務列表即時更新，以及一個保留給任意指令（`talk`／`attack`／`say`／`unlock` 等）的輸入框。

唯讀的 Studio projection 可由 CLI 或 API 取得，供 EveGlyph 的 World Overview／Diagnostics／Runtime Observatory 使用：

```bash
PYTHONPATH=src python3 -m compilableworld studio-overview build/mingyun_zhiyu_peace_city/world.package.json
```

Web Gateway 對應 `/api/studio/overview`。它只投影 FMS 世界元資料、TMS 模組、Entity／State／Quest 圖、semantic records metadata、DMS 靜態診斷與最近 Runtime Trace，不提供任何直接寫入 StateStore 的路徑。

## 玩家角色生成

玩家入口不再綁定小說主角團。Runtime 會提供幾個可修改的 AI 基本模板；模板只是玩法建議，不是《命運之欲》的 canon 角色。可列出模板：

模板現在也可放在世界自己的 Authoring Layer：在 `manifest.json` 的 `sources.player_templates` 指向一份 `player_templates.json`，編譯後才進入 Runtime Package；沒有指定時才使用引擎內建模板。

```bash
PYTHONPATH=src python3 -m compilableworld character-templates
```

啟動 `play` 或 `serve` 時，省略 `--actor` 就會建立一名新的玩家角色。模板、自訂屬性與固定 seed 共用同一個生成器：

```bash
# 套用模板
PYTHONPATH=src python3 -m compilableworld play build/mingyun_zhiyu_peace_city/world.package.json \
  --template spellblade --name 曙光旅者 --seed 42

# 隨機選模板；保留 seed 就能重現同一份角色
PYTHONPATH=src python3 -m compilableworld serve build/mingyun_zhiyu_peace_city/world.package.json \
  --random-character --seed 20260714 --port 8765

# 在模板投影後修改部分屬性（範圍 10–60）
PYTHONPATH=src python3 -m compilableworld play build/mingyun_zhiyu_peace_city/world.package.json \
  --template balanced --attrs str=20,mag=16
```

第一版生成規則沿用整合文件與 Runtime 已驗證的公式：五維地板值為 10，預設 `attribute = 10 + cumulative_power × weight`（新手 cumulative power=15）；HP=`CON×8`、MP=`MAG×5`、FP=`(MAG+DEX)×2`。自訂值會被記錄為 override；隨機生成只改變模板選擇與 seed，不會另開一套戰鬥公式。若要完全沿用舊版固定實體，可加 `--legacy-default`，或明確指定 `--actor`。

網頁入口也提供 `/api/character/templates` 與 `POST /api/character/create`，建立後會替換目前瀏覽器 actor，並回傳完整生成資料與新的 View Model。

## 測試

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Authoring Layer 也可以宣告可重播的 `ScenarioIR`。Scenario 只在記憶體中套用 `given`，再透過同一條 ActionIR／Kernel／EventIR 管線執行 `when`，最後驗證 `expect.state`、`expect.events` 與 Action status；它不會改寫正式世界資料：

```bash
PYTHONPATH=src python3 -m compilableworld scenario-run \
  build/mingyun_zhiyu_peace_city/world.package.json peace_city.find_work
```

範例世界的 `scenarios.json` 是可供 EveGlyph Scenario／Simulator 讀取的第一批情境來源。編譯器會拒絕未知目標、非法狀態欄位、重複 Scenario ID 與不合法 Action，避免測試本身偷偷變成另一套世界規則。

### FunctionIR 與公式 Registry

世界也可以在 `functions.json` 宣告受限的純函式。v0.1 只允許 numeric expression tree（`add`、`sub`、`mul`、`div`、`min`、`max`、`neg`、`clamp`、`round`），不接受任意 Python 或副作用；編譯後由 `runtime.functions` 評估，讓玩家生成、戰鬥公式與 Studio preview 共用同一個可驗證邊界：

```bash
PYTHONPATH=src python3 -m compilableworld function-eval \
  build/mingyun_zhiyu_peace_city/world.package.json math.clamp \
  --args '{"value":12,"minimum":0,"maximum":10}'
```

目前已遷移的純數值入口包括玩家屬性投影、HP／MP／FP、近戰 AR／DR、命中率、傷害與行動經濟；階級門檻、狀態衰減與 StateDelta／EventIR 流程仍由 Runtime Module 控制。每個 migrated function 都保留既有 Python 公式的 golden regression test，避免註冊化改變數值。

Function Registry 同時提供有上限的 LRU memoization（預設 2048 筆），只快取已驗證的 pure FunctionIR；命中、miss、eviction、容量與目前大小會在 `runtime.diagnostics()` 的 `function_cache` 回報。Cache 是可重建的衍生資料，不會進入 Snapshot 或改變 Runtime State。

### Authoring Schema 契約

目前版本化交換契約都放在 [`schemas/`](schemas/)，共二十三份 schema 檔；catalog 暴露十一個 current authoring/runtime contract，並保留 Action behavior v0.1–v0.7 與 StateIR v0.1–v0.5 相容來源：

- `functions.v0.1.schema.json`：FunctionIR 純公式來源。
- `scenarios.v0.1.schema.json`：ScenarioIR 的 Given／When／Then 來源。
- `runtime-package.v0.1.schema.json`：Compiler 輸出的 Runtime Package。
- `rooms.v0.1.csv.schema.json`、`exits.v0.1.csv.schema.json`：地圖房間與出口表格。
- `entities.v0.1.csv.schema.json`、`items.v0.1.csv.schema.json`：實體與物品表格。
- `state-machines.v0.5.schema.json`：在 v0.4 bounded reaction DAG 上加入最多 16 層、單一 active leaf 的 compound state；Compiler 驗證 direct parent／initial child、compound entry、ancestor transition specificity 與 leaf-only timer，v0.1–v0.4 來源仍可編譯。
- `action-behaviors.v0.7.schema.json`：有界 static phase DAG、priority conditional route、唯一 terminal、編譯期 unknown／cycle／unreachable 拒絕、單一路徑 route cursor、非遞迴 primitive child Actions、phase-entry conditions、fixed-interval retry/deadline、完成模組、並行限制與中斷事件；v0.1–v0.6 來源仍可編譯。
- `studio-world-ir.v0.1.schema.json`：EveGlyph YAML 到共用 Studio World IR 的 migration，含 bounded event_match 與 requirements。
- `studio-mapping.v0.1.schema.json`：人工確認 World IR 到 Runtime 房間、表格、EventIR、priority、reward、requirements 與 guard 的映射。

Compiler 會確認這些契約檔的 `$id`，並檢查 CSV header 是否符合必要／可選欄位，再把契約 ID 寫入 `world.package.json` 的 `schema_contracts` 與 manifest 的 `source_schemas`。這些 Schema 負責結構、欄位與版本；重複 ID、跨檔案引用、狀態可達性與事件 payload 等語意規則仍由 Compiler 驗證。Studio 可透過唯讀的 `GET /api/studio/schemas` 取得 catalog，讓 EveGlyph 不需要猜測檔名或版本。

### EveGlyph World IR migration

EveGlyph 的 `entity`、`entity_list`、`state_machine` YAML 可先匯入成診斷保留的共用 Studio World IR：

```bash
PYTHONPATH=src python -m compilableworld studio-import \
  examples/studio_village_inn \
  --out build/studio_village_inn/studio-world-ir.json \
  --plan-out build/studio_village_inn/migration-plan.json \
  --allow-invalid
```

輸出格式是 `compilableworld.studio-world-ir/v0.1`，會正規化 Entity／State Machine 並保留來源路徑、validator diagnostics 與 bounded requirements。`migration-plan.json` 會列出可沿用的明確 `location`、缺失的 room binding、未映射 EventIR、guard 語意與空白 mapping template。由於 EveGlyph seed 不一定提供房間位置、出口拓撲或 Runtime QuestModule event mapping，輸出明確標示 `compile_ready: false`；它是共用 migration artifact，不是偷偷生成的 Runtime Package。

也可以先產生一份只含明確候選、未知欄位保留 `null` 的 mapping 草稿：

```bash
PYTHONPATH=src python -m compilableworld studio-suggest-mapping \
  build/studio_village_inn/studio-world-ir.json \
  --out build/studio_village_inn/studio-mapping.json
```

這個命令只做 deterministic suggestion，不會替未知事件或 guard 語意做猜測；草稿必須人工補完後，才交給下一個驗證命令。

填完人工映射後，可用同一份 World IR 做 fail-closed 驗證：

```bash
PYTHONPATH=src python -m compilableworld studio-validate-mapping \
  build/studio_village_inn/studio-world-ir.json \
  build/studio_village_inn/studio-mapping.json
```

驗證只回報 `mapping_complete`／`runtime_ready` 與診斷，不會修改 World IR 或 Runtime State；World IR 本身有 validation error、同一 `from/on/priority` 選出不同 target，或含 `external_review` 等尚未具備 Runtime 語意的 guard policy 時，流程會 fail-closed。只有欄位完整且沒有來源錯誤時，`mapping_complete` 才會是 `true`；guard policy 仍會讓 `runtime_ready` 保持 `false`。

## 範例世界

- `examples/gray_crown` — 原始參考範例（示範資料）。
- `examples/mingyun_zhiyu_peace_city` — 真實內容切片，改編自 Neo.K 的《命運之欲》小說世界觀（透過既有的 `worlds/mingyun_zhiyu_peace_city/world-ir.yaml`，見 CompilableWorld-Evennia-Reference 姊妹 repo；世界觀 canon 資料庫本身在 `worlds/mingyun_zhiyu/data/` 已擴充到 16 城/48 具名角色/公理/魔法系統等規模，本切片仍只用了和平之城賤民區這一小塊，其餘 canon 尚待未來擴充）。「找份差事」示範了完整的互動小說小閉環：先與老鐵交談，`dialogue.responded` 促使 QuestModule 把任務由 `unstarted` 轉為 `available`；再交付柴薪，任務轉為 `completed` 並發放報酬。北境關卡再往北是 `room.north_garrison`（北境軍營），駐守著具名 canon 角色**沃爾坎·鐵壁**（`worlds/mingyun_zhiyu/data/drafts/characters_peace_city_subtop50.csv` 的 No.13，數值取自 `combat_resolution_system.json` 自己的驗算範例，非另行編造）——玩家（新來者，地板值屬性、tier0）與他交手會實際觸發公式判定路徑，親身體驗「突破門檻」機制：命中率被壓到約 0.2%，20 次攻擊全部落空是預期結果，不是 bug。

在 CLI 中依序輸入（以 `examples/mingyun_zhiyu_peace_city` 為例，完成「找份差事」任務，並可繼續北上見識沃爾坎）：

```text
take 臨時身份牌
n
w
talk 老鐵 work
e
take item.firewood_bundle
w
give item.firewood_bundle npc.foreman_laotie
talk 老鐵 work
quests
status
e
unlock 北境關卡鐵柵欄
open 北境關卡鐵柵欄
n
n
attack 沃爾坎
```

或以 `examples/gray_crown` 驗證上鎖門與抵達型任務：

```text
take item.old_key
n
unlock door.old_vault
open door.old_vault
d
look
diag
save demo-save.json
```

## 架構邊界

```text
JSON / CSV / Manifest
        ↓ compiler + validators
Runtime Package (World IR subset)
        ↓ loader
World Kernel
        ↓ Action IR
MSSP TMS Module
        ↓ StateDelta + EventIR
Atomic Commit / Event Log / Projection
        ↓
Terminal Gateway  |  Web Gateway (View Model -> HTML/JS)
```

Python 版本用於凍結語言無關契約與快速驗證。後續 Rust 重寫應保持 Runtime Package、Action IR、State Delta、Event IR 與 Module Contract 的語義相容，而非逐行翻譯 Python 類別。

### 狀態感知場景敘事

可選的 `narrative.json` 會在編譯期驗證，並產生唯讀的 `room_overlays`。每條規則以 `owner`（可用 `$actor`）、`namespace`、`key`、`equals` 比對 State Store；命中時可 `append` 或 `replace` 房間基底描述。`look`、終端顯示和 Web View Model 共用同一個 projection，因此任務完成或角色死亡後的文字不會因入口不同而分歧。這不是新的可寫狀態，也不會讓 UI、Narrator 或記憶模組取得 `StateStore` 寫入權。

### 資料驅動 NPC 對話

可選的 `dialogues.json` 是和 `narrative.json` 平行的 Authoring Layer 來源。每筆資料固定包含 `dialogue_id`、`speaker_id`、`topic`、`when`、`text`；編譯器會驗證說話者確實是 `character` 或 `creature`、所有條件只讀取白名單狀態，以及 ID／型別沒有漂移。`when: []` 表示該話題的無條件回退行；條件可引用 `$actor`，NPC 自身則可引用 `$speaker`。

玩家可輸入 `talk 對象 [topic]`（`ask` 是別名）。Runtime 只會在對象存在、同房間、仍能回應時選出對話，依序採用「指定話題 → `default` 話題」與「較多滿足條件優先、同分依來源順序」的固定規則，然後發出 `dialogue.responded` EventIR。這是**唯讀投影**：DialogueModule 不會直接寫入任務、貨幣或角色狀態；若有對話帶來劇情進度，必須由 `quests.json` 明確宣告的 QuestModule EventIR 轉移來寫入。CLI、Web、AMK Raw 捕捉因而共用同一份事件事實。

### 可編譯任務轉移

原有任務可維持簡單的 `requirements`／`reward` 格式；新的多階段任務則改用 `transitions`，每條邊含 `transition_id`、`from`、`on`、`to`，並可附加 `event_match`、`requirements`、完成報酬與 bounded `priority`。觸發白名單已涵蓋 action failure、移動、物品、門、對話、戰鬥、魔法與 terminal quest chaining；每種 EventIR 可比對的 payload 欄位都由共用契約限制，並在 Studio mapping 與正常 Compiler 兩層 fail-closed 驗證。完整順序與邊界見 `docs/WORLD_STATE_MACHINE_EXECUTION_CONTRACT_zh-TW.md`。

Runtime 收到事件後只會為該 actor 的目前狀態選邊；較高 `priority` 勝出，同一 `from/on/priority` 則在編譯期直接拒絕，避免用作者列表順序偷偷裁決衝突。進入 `completed` 會發出 `quest.completed`，進入 `failed` 會發出 `quest.failed`，每次轉移都會先發出可追溯的 `quest.transitioned`。這些寫入都走 `WorldRuntime.commit_reaction()` 的原子 Delta+Event 路徑。

### Scoped StateIR 世界狀態機

`state_machines.json` 現在可宣告 World／Region／Scene／Entity／System 五種 owner scope。v0.5 加入 bounded compound hierarchy，但每台機器仍只有一個 active leaf；compound target 依唯一 initial-child chain 解析，事件 transition 可由 leaf 或 ancestor 匹配，同 priority 時較深 source 勝出，timer source 則必須是 leaf。EventIR／StateStore conditions、64 層內 reaction DAG 與 4096-event cascade safety rail 均沿用既有 fail-closed 邊界。Runtime 只允許每台機器寫入自己的 `owner::fsm::<state_machine_id>` active leaf，以及有 timer 時由 Compiler 保留的 `owner::fsm_runtime::<state_machine_id>` entry tick；所有寫入仍經同一筆 StateDelta／EventIR 交易。

Runtime EventBus 會以同步 FIFO 派送已提交的 EventIR batch；reaction 新事件排在既有 batch 後方，不再遞迴插隊。每個 root cascade 最多派送 4096 個事件，超限會清空尚未派送佇列並直接把 audit-only、不可再觸發 reaction 的 `runtime.reaction_halted` 寫入 EventLog；Replay 會驗證並還原這個停止診斷。

Timer 使用既有 Kernel scheduler tick，不讀牆鐘也沒有背景執行緒。條件未成立時保持 eligible；成立後由最高 priority 唯一選邊，並發出 `fsm.timer_elapsed` → `fsm.transitioned`。Gray Crown 的安全系統以 authored target `incident` 進入 initial leaf `breached`，兩 tick 後自動轉為 sibling leaf `contained`。Lifecycle payload 同時保留 authored `from/to` 與實際 `from_leaf/to_leaf`，Replay 可驗證 compound entry；entry tick 仍是 StateStore 的保留 metadata，不需第二個 timer queue 或新 Snapshot 格式。

owner scope 表示狀態所有權、condition owner 與可見性，不會自動把事件限制在某個地區或房間；需要地域路由時，authoring 必須用事件型別與 `event_match` 明確表達。OR／NOT 群組、自由文字 guard、任意 effects/reward、牆鐘／日曆／週期 timer 與 Runtime random sampling 仍不在此契約內；Action-scope 複合行為則由獨立契約控制。完整規格見 `docs/SCOPED_STATE_IR_EXECUTION_CONTRACT_zh-TW.md`。

### Action-scope 複合行為

`action_behaviors.json` 可將一個玩家 verb 綁定到 2–64 個靜態 phase node，每個 node 有 1–1,000,000 tick duration，authored node 總長仍不得超過 1,000,000 tick。v0.7 以第一個 node 為 entry、要求唯一 terminal；每個非 terminal node 有 1–16 個 static `next_phase_id` branch，整體至少一個 split。Compiler 拒絕未知 target、self-route、cycle 與不可達 node，並以最長 entry-to-terminal path 作為排程上限。Kernel 依 bounded AND conditions 選 branch，nullable primitive child 完成且 target gate 通過後才原子推進 route cursor；選擇與成功 child 都是 sticky，retry 不會重選或重跑。進入 terminal 時 due tick 會收斂到實際路徑。child 仍只能繼承父 actor、使用白名單 verb／module／target／args，不能遞迴 authored behavior；最後效果仍由唯一 completion module 提交。

Gray Crown 的 `search` 保留為 v0.6 相容切片：第一 tick 依 actor alive 選擇 `look` 或 `status` child，再 implicit rejoin 到 `inspect`。v0.7 測試切片另驗證三 tick 長路徑 `survey -> focus -> inspect` 與兩 tick短路徑 `survey -> inspect`；短路徑在第一個 boundary 將 due tick 從 3 收斂為 2。終端／Studio projection 顯示安全的 branch／step／condition ID、`next_phase_id`、visited path 與 retry deadline，不公開 child args 或條件值。Snapshot v0.6 與 EventLog Replay 都可重建 route cursor、due tick、branch choice、retry state 與 completed child path。完整規格見 `docs/ACTION_SCOPE_BEHAVIOR_EXECUTION_CONTRACT_zh-TW.md`。

### Snapshot 與排程恢復

`save_snapshot` 使用 `compilableworld.snapshot/v0.6`，除了 Runtime State、動態玩家、生成 profile、目前 tick 與排程 Action，也保存 pending Action 的 route cursor、retry attempt／deadline、`selected_branches` 與實際路徑 `completed_steps`。載入時會驗證 route node、visited edge、active retry target、phase／queue due tick 與 authored branch；舊 `v0.1`–`v0.5` 仍有明確 migration，legacy Action 的 route 為 null。

### AMK v0.1（可選的受治理記憶核心）

`agent_memory_kernel` 是零第三方依賴的本機 Raw／Clean 記憶服務。Raw JSONL ledger 與 SQLite metadata 是可稽核證據層；Clean entry 必須經過 evidence、scope、attribution 與 reviewer separation 驗證，不能由 Agent 或 Narrator 自動晉升。它不取代 Runtime State、Event Log 或遊戲存檔。

直接使用 AMK：

```bash
PYTHONPATH=src python3 -m agent_memory_kernel init build/amk/demo.db
```

執行遊戲時加入 `--amk-db`，Runtime 的 `EventIR` 會被**唯讀地**寫入 AMK Raw evidence；未提供該參數時，遊戲行為完全不依賴 AMK。若本機記憶儲存失敗，預設只記錄 adapter 狀態，不會把已提交的世界行為改成失敗。

```bash
PYTHONPATH=src python3 -m compilableworld play build/gray_crown/world.package.json \
  --amk-db build/amk/gray-crown.db --amk-tenant local --amk-owner user.neok
```

以 editable mode 安裝後，也可使用 `amk-local` 命令。`amk-local --help` 列出 Raw capture、candidate proposal、分離 reviewer 審核、Context Packet、checkpoint 與 index rebuild 操作。

## 已知邊界

- 目前是單程序、單世界實例；沒有帳號、多人網路與分散式鎖。
- Scheduler 已支援版本化 Action-scope 行為、生命週期、取消、中斷、pending 投影、Snapshot 與 Replay；Studio 目前只有唯讀 overview，尚未提供視覺化 authoring/write-back 表單。
- 房間有可選的 `narrative.json` 條件式文字投影；NPC 有可選的 `dialogues.json` 單回合、狀態感知對話，兩者都由 CLI 與 Web 共用。已能由對話事件接取任務，但尚未實作多輪對話 session、玩家可見的選項卡、語義理解與 AI 生成敘事。`visible_entities` 仍會標示實體是否存活（終端機顯示「（已死亡）」，網頁介面同步）。
- Quest 模組保留原有的兩種事件驅動 requirement（`deliver:<item>:<target>`、`reach:<room>`）與貨幣報酬，並新增顯式的多階段／分支／失敗 transition。未知 requirement、未知事件欄位、終態再轉移與同優先權分支衝突都會在編譯期 fail closed。尚未支援：複合布林條件、時間／排程觸發、回復／撤銷轉移、道具型報酬與執行期生成新實體。
- World／Region／Scene／Entity／System 的 scoped StateIR 已可透過 EventIR 跨層轉移，並有 bounded single-active-leaf compound hierarchy、owner／actor StateStore AND conditions、deterministic leaf timer、明確非終態 DAG 串接與 4096-event Runtime cascade safety rail；Action-scope 也已有可中斷／取消的 bounded v0.7 static phase DAG、sticky priority route、單一路徑 merge、primitive child sequence、phase-entry AND gates 與 fixed-interval retry/deadline。兩者都尚未支援地理感知的自動事件路由、OR／NOT 或自由 guard、nested/dynamic/recursive graph、resume／補償交易、自由 backoff/jitter、parallel 或 synchronizing join。
- Intent Parser 是確定性參考實作；AI Adapter 必須輸出同一 `ActionIR` 並接受 Kernel 驗證。
- Module Contract 的寫入範圍已由 Kernel 強制檢查；讀取範圍與 Action authority 的強制隔離留待 v0.2。
- 核心 JSON／CSV Schema 已外部化為 `schemas/` 下二十三份契約檔（含 Action behavior v0.1–v0.7 與 StateIR v0.1–v0.5 相容契約）；CSV header、scoped StateIR、Action-scope behavior、EveGlyph World IR migration 與人工 mapping validation 已接入，跨檔案引用與其他語意規則仍由 Compiler 驗證。
- Replay 重放已提交 Delta；跨版本重放仍需 migration registry。
- 戰鬥有兩條判定路徑，同一場戰鬥不會混用：(1) **簡易路徑**——命中率 85%、傷害區間 3-7、`combatant` component 存活反擊機率 75%（區間 1-3），取材自對真實 LPC MUD（mhsj）戰鬥系統的研究，見 `docs/whitepapers/`；(2) **公式路徑**——當雙方都在 `entities.csv` 填了完整五維屬性（`str/con/mag/agi/dex` + 選填 `phase_tier`）時自動啟用，直接還原 `worlds/mingyun_zhiyu/data/drafts/combat_resolution_system.json`（Neo 已審閱核准）的比率制命中/傷害/突破門檻公式**與交鋒（Exchange）先攻回合制**——一次 `attack` 指令＝一次交鋒，`IV=AGI+0.5×DEX` 決定雙方各自的行動次數（`clamp(round(IV_己方/IV_對方),1,4)`），較快一方的行動全部先解算完才輪到較慢一方（來源文件是敘事上的交錯描寫，這裡簡化成「先攻方全部行動完再輪下一方」，非逐拍交錯，有明確記錄不是隱藏簡化）。見 `src/compilableworld/combat_formulas.py`，`tests/test_combat_formulas.py` 用該文件自己的 worked example（露芙緹雅 vs 格洛森、IV比值3.2→3次行動）逐位數比對回歸測試。`examples/mingyun_zhiyu_peace_city` 的 `player.newcomer`（地板值屬性，tier0）與 `npc.woerkan`（真實 canon 數值，tier1）雙方都已授權屬性，實際觸發公式路徑；`creature.sewer_rat`／`npc.guard` 等舊有戰鬥實體刻意留在簡易路徑——公式常數（HP=CON×8、傷害×0.1縮放）是為數百點屬性的正式 canon 角色校準的，硬套在地板值內容上會異常緩慢/肉質過厚（實際算過，不是猜測）。五維屬性欄位為全有全無（部分填寫會編譯失敗），且與舊版 `health` 欄位互斥（HP 改由 CON 推導）。
- 規則魔法施法系統（同一份 `combat_resolution_system.json` 的 `rule_magic_casting_system`）已實作 MP/FP 資源池（由 MAG/DEX 在編譯期自動推導，五維屬性齊全的實體都會有）與 `cast <法術名>` 指令，目前接了兩個法術：`護盾術`（5 符號，MP40/FP25，temp_HP=施法者MAG×2，優先於真實生命值承受傷害，且與其他狀態一樣持續 3 次交鋒——耗盡或到期兩者先到者為準）、`疾風步`（3 符號，MP24/FP15，IV×1.5 持續 3 次交鋒；symbol_count=3 是本專案自己從 `combo_home` 標籤數推斷的，來源文件沒有給這個法術的具體數字，跟 `護盾術` 是文件自己給的範例不同）。異常狀態現在是一個真正通用、會隨交鋒衰減的機制（`combat.status_effects`，見 `combat_formulas.py` 的 `refresh_status`／`decay_status_effects`），不是只為了護盾寫死的一次性欄位——`疾風步` 直接證明這點：它改的是先攻回合制的行動次數，不是傷害或血量。**刻意未實作**：多交鋒引導詠唱（`cast_time_exchanges>1` 的高階法術，需要在交鋒之間插入「引導中斷判定」，目前交鋒已實作但引導/中斷邏輯還沒有——本輪也刻意簡化成「施法本身不消耗交鋒」，跟來源文件嚴格定義有落差，已記錄）；完整的異常狀態框架其餘 9 種（麻痺/破綻/凍傷/束縛/靜默等，目前只做了 shield_buff／haste_疾風 兩種，通用的衰減/刷新機制已就位，加新狀態的邊際成本應該不高）；近戰以外招式（`ranged_precision_physical`／`mental_spiritual` 這兩種攻擊類型公式已在來源文件定義好，尚未接線）。這些是該檔案裡份量最大的剩餘部分，留待未來階段。
- Web Gateway 是單一 actor、單一瀏覽器分頁假設下的 request/response API（無 WebSocket、無帳號/session），與已知的單程序/單世界限制一致；`/api/action` 與 `/api/state` 共用同一把 lock 序列化存取，避免併發提交造成的版本衝突，但不是為多人設計的。
- AMK v0.1 已提供本機 Raw/Clean、治理與 CompilableWorld EventIR 唯讀擷取；它目前沒有向量／圖／時間索引、真正網路同步、加密副本、背景自我改寫或直接程式碼／權重寫入。它不是 Runtime State，也不會自動把遊戲事件升格為 Clean truth。
- （已修復，記錄供參考）CLI 曾在非 UTF-8 系統 locale（例如繁體中文 Windows 的 cp950）下對含中文標點的 `say` 輸入拋出編碼錯誤；`cli.py` 現在會在啟動時強制 stdin/stdout 為 UTF-8。
- （已修復，源自一次真實的 AI 玩家試玩）指令目標現在可以用場景內可見的顯示名稱（例如「老鐵」）指定，不再強制要求內部 ID（`npc.foreman_laotie`）——`DeterministicIntentParser` 會在目前房間與玩家物品欄中做名稱解析，找不到或有歧義時一律不猜測、原樣傳給下層模組，讓玩家看到正常的「找不到」訊息，不會誤觸錯的目標。同一輪試玩也發現 `give` 沒有保護機制、可以把仍在使用中的鑰匙道具送給不相關 NPC 且無法復原——現在會在該鑰匙鎖著的門還沒開之前擋下交付。另外修正：裸方向詞（`north`）現在可直接使用；`unlock` 對非門實體會給出正確訊息而非誤導的「門沒有上鎖」；戰鬥現在有反擊傷害與獨立的擊殺訊息。

## Read-only MCP 世界介面（M0）

`compilableworld_mcp` 提供一層不修改 `StateStore` 的世界存取服務，直接重用既有 Runtime Package、WorldRuntime、Web View Model 與 EventLog。核心服務維持零第三方依賴；只有真正啟動 MCP 傳輸時才需要安裝官方 Python SDK v1.x：

```bash
python -m pip install -e ".[mcp]"
```

啟動 stdio MCP Server：

```bash
cw-mcp-readonly build/gray_crown/world.package.json
```

或啟動可供 MCP Inspector 連線的 Streamable HTTP：

```bash
cw-mcp-readonly build/gray_crown/world.package.json --transport streamable-http
```

M0 只暴露 `list_worlds`、`open_world_session`、`get_world_status`、`get_current_scene`、`get_recent_events`、`close_world_session`。所有結果均標示 `read_only: true` 與 `world_state_changed: false`；尚未提供 `submit_action`、遠端驗證、多人一致性或 Drive 回寫。完整邊界見 [`docs/MCP_READONLY_M0.md`](docs/MCP_READONLY_M0.md)。
