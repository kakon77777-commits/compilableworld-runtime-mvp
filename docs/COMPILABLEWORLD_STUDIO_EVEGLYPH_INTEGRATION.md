# CompilableWorld Studio × EveGlyph 整合界線

正式主線已吸收昨天的 Studio 論文與 EveGlyph 的 `village-inn` World IR 種子，但兩個專案的責任保持分離：

- `D:\Ai\work together\eveglyph-editor`：表單、表格、狀態機圖、Markdown／YAML 編輯、Agent Diff Review。
- `D:\Ai\work together\compilableworld-runtime-mvp`：Authoring Layer 編譯、Kernel、Module Contract、Runtime State、EventIR、Snapshot 與可重現執行。
- `D:\Ai\work together\CompilableWorld-Evennia-Reference`：舊 Evennia 參考庫，不是正式 Studio 或 Runtime。

## 已移植內容

- `docs/whitepapers/09-compilableworld-studio-mssp-rdr-visual-world-ide-v0.1.md`：正式主線保存的 Studio 架構規格。
- `examples/studio_village_inn/`：EveGlyph 可視化 World IR 的 Entity／State Machine／故意損壞案例。它是 Studio authoring seed，尚未偽裝成 Python Runtime Package。
- `src/compilableworld/studio_world_ir.py`：零第三方依賴的 EveGlyph YAML subset importer，輸出診斷保留的共用 Studio World IR JSON，並保留 state machine 的 variables／events／instructions／responses、受控 random 描述、bounded event_match 與 bounded requirements。
- `src/compilableworld/studio.py`：零第三方依賴的 headless projection，輸出 FMS／SMS／TMS／DMS、Quest graph、靜態 diagnostics 與 Runtime Trace tail。
- `state_machines.json`：版本化的 World／Region／Scene／Entity／System StateIR；v0.4 支援 EventIR、bounded deterministic tick timer，以及明確來源、無循環、最多 64 層的非終態 `fsm.transitioned` DAG。Studio overview 可唯讀顯示 owner、狀態圖、初始／目前 state、entry tick 與 pending timer countdown。
- `action_behaviors.json`：版本化的 Action-scope 行為來源；v0.7 可宣告 compile-time static phase DAG、priority conditional `next_phase_id` route、唯一 terminal、非遞迴 primitive child Actions、bounded phase-entry conditions 與 fixed-interval retry/deadline。Studio authoring overview 可唯讀顯示 execution model、entry／terminal、完整 branch target／child／條件／policy；player/runtime pending projection只顯示安全 route／visited path／retry progress。正式修改仍回到 authoring source。
- `scenarios.json`：正式的 ScenarioIR Given／When／Then 來源，編譯後由 `scenario-run` 以正常 Runtime 管線重播。
- `functions.json`：正式的 FunctionIR 純公式來源；只允許受限 numeric expression tree，編譯後由 `runtime.functions` 評估。

## 契約

`package_overview(package)` 與 `/api/studio/overview` 都是唯讀投影，並會在 `semantic_records.metadata_only: true` 下提供 `package.studio.semantic_records`。它們不能修改 Authoring Layer、Compiled Package 或 Runtime State；任何世界變更仍必須回到來源資料、Compiler 與測試流程。

v0.4 的非終態 `fsm.transitioned` 是 reviewed `state_machines.json` 的直接 StateIR 契約。現行 `studio-compile` 的 state-machine overlay 仍只產生 `target: quest`，因此 mapping validator 會以 `nonterminal_stateir_only` 拒絕把這個事件偽裝成 Quest overlay；EveGlyph 可先顯示與編輯候選，但要由 StateIR write-back／Compiler 完成來源、cycle 與 depth 審查。

目前 EveGlyph 的 `kind: entity`、`kind: entity_list`、`kind: state_machine` YAML 文件仍是 Studio 編輯格式；現在已有正式的 `studio-world-ir/v0.1` migration artifact，但它刻意不直接編譯成 Runtime Package。`cw-runtime studio-import` 會保留來源文件、正規化 entities/state machines（含語義 records）、診斷與 `compile_ready: false`；房間／出口映射與 Runtime QuestModule event mapping 仍需明確 authoring diff，不能由 importer 猜測。

通過 `studio-compile` 後，語義 records 只進 `package.studio.semantic_records`，並標示 `semantic_records_are_metadata_only: true`，不會被 Runtime Kernel 執行。

EveGlyph 的 Studio 面板也可以把目前 draft POST 到 Runtime 的唯讀 `/api/studio/import`。這個端點只解析與產生 World IR／diagnostics／mapping suggestion，不取得 Runtime State 寫入權；Runtime URL 沿用 Runtime 面板設定，預設為 `http://127.0.0.1:8765`。EveGlyph 可編輯 mapping JSON，再 POST 到 `/api/studio/validate-mapping` 取得 `mapping_complete`／`runtime_ready` report；這仍不會直接編譯或安裝 Runtime Package。

ScenarioIR 是兩者目前最直接的交界：EveGlyph 可以提供表單／情境編輯與 Diff Review，Runtime 只接收編譯後的 scenario contract，並回傳可稽核的 action 結果、State assertion 與 EventIR 序列。

FunctionIR 是目前已啟用的共用交界：玩家屬性投影、HP／MP／FP、近戰 AR／DR、命中率、傷害與行動經濟都可由 package 的純 AST 評估。EveGlyph 後續可以編輯公式、顯示輸入輸出預覽與靜態診斷；Runtime 只執行已通過 schema 驗證的純 AST。階級門檻與狀態衰減仍屬 Runtime Module 的控制流程，不會被偽裝成單純算術。

EveGlyph 的 Runtime 面板使用兩個唯讀端點：`GET /api/studio/functions` 取得 catalog，`POST /api/studio/function-preview` 以 `{function_id, inputs}` 取得結果。編輯仍發生在 `functions.json` 與 reviewed diff；preview 只讀取已編譯 package，不會寫入 Runtime State。

## Authoring Schema catalog

正式主線現在把交換邊界外化成 [`schemas/`](../schemas/) 下二十二份 schema；catalog 暴露十一個 current authoring/runtime contract，Action behavior 同時保留 v0.1–v0.7，StateIR 保留 v0.1–v0.4：

- `functions.v0.1.schema.json`：FunctionIR 純數值公式來源。
- `scenarios.v0.1.schema.json`：ScenarioIR Given／When／Then 來源。
- `runtime-package.v0.1.schema.json`：Compiler 到 Runtime／Studio 的套件契約。
- `rooms.v0.1.csv.schema.json`、`exits.v0.1.csv.schema.json`：地圖表格欄位契約。
- `entities.v0.1.csv.schema.json`、`items.v0.1.csv.schema.json`：實體／物品表格欄位契約。
- `state-machines.v0.4.schema.json`：五種 owner scope、EventIR／bounded tick timer 選邊與 owner／actor StateStore AND conditions；`fsm.transitioned` 必須鎖定來源 machine + transition，Compiler 驗證來源、靜態 payload、無循環與 64 層深度；`v0.1`–`v0.3` 檔案保留為來源相容邊界。
- `action-behaviors.v0.7.schema.json`：Action-scope static phase DAG、priority conditional route、編譯期 graph closure、單一路徑 route cursor、非遞迴 primitive child Actions、bounded conditions、fixed-interval retry/deadline、完成模組、並行限制與中斷事件契約；`v0.1`–`v0.6` 檔案保留為來源相容邊界。
- `studio-world-ir.v0.1.schema.json`：EveGlyph YAML 到共用 Studio World IR 的 migration 契約。
- `studio-mapping.v0.1.schema.json`：人工確認 World IR 到 Runtime 的 room、table、EventIR 與 guard 映射契約。

Compiler 會在編譯時確認 `$id`、CSV header 與 manifest 的 `source_schemas`，並在 `world.package.json` 寫入 `schema_contracts`。`GET /api/studio/schemas` 只回傳版本、檔名、標題、類型與可用性，供 EveGlyph 做契約選擇與 UI 提示；不提供任何修改或直接寫入 Runtime State 的能力。Schema 的結構驗證與 Compiler 的跨檔案語意驗證是兩層責任：例如 duplicate ID、已知 entity/item 引用、Quest graph 可達性與 EventIR payload 白名單仍由 Compiler 保持 fail-closed。

## EveGlyph World IR migration

匯入單一 YAML 或整個 EveGlyph seed 資料夾：

```bash
PYTHONPATH=src python -m compilableworld studio-import \
  examples/studio_village_inn \
  --out build/studio_village_inn/studio-world-ir.json \
  --plan-out build/studio_village_inn/migration-plan.json \
  --allow-invalid
```

`--plan-out` 會另外輸出 `compilableworld.studio-migration-plan/v0.1` mapping 草稿，列出已明寫的候選位置、缺失的 room binding、未映射 EventIR、guard 語意與待填 template。`--allow-invalid` 只代表保留含故意損壞案例的診斷輸出；它不會把 invalid 文件標成可執行。未提供此旗標時，只要有 error diagnostic，CLI 會回傳失敗。這個 JSON World IR 是 Studio／Agent review 的交換物，不會寫入 Runtime State，也不會跳過既有 Compiler。

填完 `studio-mapping/v0.1` 後，用 `studio-validate-mapping` 驗證所有 entity room、state-machine transition EventIR 與 guard policy 是否已明確填寫。驗證器只產生 report，不修改 World IR 或 Runtime State；若 World IR 已有 validation error，或同一 `from/on/priority` 會導向不同 target，mapping 會直接 fail-closed。`mapping_complete` 代表來源與欄位都完整，`runtime_ready` 另會排除尚未具備可執行語意的 `external_review`／`drop_with_approval` guard policy。

若要先建立工作檔，可執行 `studio-suggest-mapping`。它只會沿用來源明確寫出的 room 與已知 EventIR，其餘欄位保留 `null`，並把含自由 guard 的 state machine 標成 `external_review`；這是 review draft，不是可直接執行的 Runtime mapping。

只有 mapping report 的 `runtime_ready: true` 才能進入 `studio-compile`。它需要一個完整的 base Runtime Authoring Layer，將明確映射的 entities/items 與 `target: quest`、無自由 guard 的 state machines 暫存 overlay 後交給既有 Compiler；base source 不會被修改，語義 records 仍以 package metadata／review artifact 保存，不會被偷偷當成可執行 Python 規則：

每個 semantic record bundle 最多 128 筆、合計最多 4,000,000 UTF-8 bytes。

Studio transition 的 `requirements` 只接受 `reach:room_id` 或 `deliver:item_id:target_id`，最多 32 條；mapping 必須完整保留來源條件，最後再由正常 Compiler 驗證 room／item／target 是否存在。

Studio transition 的 `priority` 限定為 0 到 1,000,000 的整數；`reward` 只允許轉入 `completed` 的 currency-only 報酬，currency 限定為 0 到 1,000,000,000。mapping 需完整保留這兩個欄位。

Studio transition 的 `event_match` 最多 16 個欄位，值只能是 JSON scalar，且 mapping 後會依目標 EventIR 的 payload 白名單再次檢查；不符合時停在 review artifact，不會進入 Runtime package。

```bash
PYTHONPATH=src python -m compilableworld studio-compile \
  examples/mingyun_zhiyu_peace_city \
  build/my-draft/studio-world-ir.json \
  build/my-draft/studio-mapping.json \
  --out build/my-draft/runtime
```

FunctionIR 的 Registry 目前也實作 RDR L3 的最小形式：有容量上限的 LRU memoization。它只作用於已驗證的 pure numeric function，Runtime diagnostics 會暴露 hits／misses／evictions；因此 Studio 可以觀察重用效果，但不需要把 cache 當成世界內容或存進 Snapshot。
