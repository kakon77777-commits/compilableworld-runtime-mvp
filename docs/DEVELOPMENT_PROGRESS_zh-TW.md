# CompilableWorld 每日施工進度

## 工作節奏

2026-09-10 為重新施工第 1 天。依使用者決定，每天完成一個可驗收的工作包，主力模型偏好 GPT-6（目前 `gpt-6-astra`）。一個工作包包含需要的實作、測試與文件；不以對話數、小檔案數或版本編號代替成果。

目前由使用者回到本 task 時啟動當日工作。自動排程的時段尚未指定，尚未建立自動執行。模型偏好限本專案，沒有變更其他 task 的設定。

## Day 1 — 2026-09-10：施工基線合流

**狀態：COMPLETE（限本日施工基線驗收）**

### 基線來源

- 本機既有成果：`c151a9659a4152a8a30842c2df20bee02eca722a`，含 StateIR v0.6、玩家建立、entity membership 與 snapshot restore Replay 修正。
- GitHub 主線來源：`cf37f539e0807499e8b337f80a5f152324c087f2`，含 create-only `EntityTransactionRuntime` 與原始測試。
- 來源文件保存 commit：`9301bf3`，保留 5 篇 CRDWS paper、9 篇 RGGD 正文、總索引及來源 manifest。
- 經驗證合流 commit：`89b6d71f48263482dbf4e887c01c203f2348ef09`；其 parents 為文件保存線與遠端 `cf37f53`。
- 合作分支：`agent/crdws-day01-baseline`。既有主分支未被覆寫。

### 本日變更

1. 合流本機與遠端成果，保留兩邊 Git 歷史。
2. 補上實體交易擴充的兩項合流相容性：純延遲 Action 的生命周期紀錄，以及整批提交事件先於反應事件的 FIFO 次序。
3. 新增 3 個可先重現失敗的回歸案例：延遲成功、延遲拒絕、反應事件排序。
4. 保存原始研究文件；以 `.gitattributes` 保留來源 byte，避免換行自動轉換破壞 manifest 雜湊。
5. 修正整合分析的本機／遠端基線混淆、補上 Object Re-entry 驗收，撤回未校準的完成輪數。

### 驗證紀錄

- 執行環境：Windows、Python 3.14.5、pytest 8.4.2；核心命令設定 `PYTHONPATH=src`，使用 `python -B`。
- 合流未修正前既有完整 corpus：`python -B -m pytest -q -p no:cacheprovider` → **365 passed**。
- 新增見證先執行：`tests/test_entity_transaction.py` → **3 failed / 5 passed**；失敗原因為預期的 lifecycle 缺失及反應排序不一致。
- 最小修正後 focused gate：entity transaction、EventBus、Action behavior → **60 passed**。
- 修正後完整回歸：`python -B -m pytest -q -p no:cacheprovider` → **368 passed**（25.35 秒）。
- Governing Twin 在修正後程式上提出 scoped **CONCUR**，另跑窄測試 **14 passed**；Kernel blob 與 `c151a96` 相同，實體交易擴充 blob 為 `33c44941a36a5ed805c06af0f36540c1ec3ca501`。
- 以 `89b6d71` 建立 detached Git worktree；15 份來源文件逐一核對 byte length 與 SHA-256 → **15 matched / 0 mismatches**，工作樹無修改。
- 乾淨 checkout 的 `tests/test_entity_transaction.py tests/test_player_generation.py tests/test_event_bus.py` → **21 passed**；兩個 example 的 CLI `validate` 均回 `ok: true`。
- 原始 paper 的 Markdown hard-break 空白保留；不為格式檢查更動來源正文。新增工程差異的 `git diff --check` 通過。

完整測試與重建結果均綁定上述程式版本及本機 Python 環境；不宣稱遠端 CI、Linux 或其他 Python 版本也在本日重跑過。之後只有本進度文件的完成紀錄更新，Runtime／tests 未再變更。

### 本日驗收邊界

本日完成條件為「兩條既有成果線可共同使用，合流回歸有測試，原始文件可重新取得並校驗」。不將一般 entity creation 的成功宣稱為通用生成物 Replay 已閉合。

CRDWS Paper 02–04 仍缺；傭兵之盾仍為 `NOT_RESEARCHED`。Domain Graph、FDCS、多速率、通用 RGGG、動態 Grammar 與完整示範遊戲仍是後續工作。

## 2026-09-11 方法交接：下次施工採用 GCT

使用者交付 GCT v1.0 與 Global-First Completion 技能包，指定明天施工時採用。原文、技能與來源雜湊已保存於 [方法採用記錄](methods/gct-v1.0/ADOPTION.md)。這次只完成方法交接，未將 Day 2 功能標為已完成，也未建立自動排程。

下一個工作包按 GCT 先實作完整路徑，再整體驗證與批次修復；採用相稱的測試，直接完成已授權範圍內的剩餘工作。

## Day 2 — 2026-09-11：通用實體的保存與 Replay

**狀態：COMPLETE（限 create-only 物件的保存、Replay 與繼續行動）**

起點 `6ba1b3e`，合作分支 `agent/day02-entity-replay`。採 GCT 將 Runtime 還原、例外回復、持久 log 重開、測試與離線示範一起接通，再集中驗證。沒有開啟自動排程或付費模型調用。

整個交付範圍是：以 create-only `EntityDelta` 建立一個普通物件，接通 Snapshot 與完整 EventLog Replay，重建同一 entity membership、state 與 lineage，並可繼續執行 Action。把所需 Runtime／版本契約、保存與重播路徑、失敗處理及正反例一起完成後驗證；共通失敗按根因批次修復。不在同一工作包加入 Domain Graph 或動態 Grammar。

本次沿用 Snapshot v0.6 與既有 EventIR v1 payload，補上 create-only Replay 的 creator binding、交易配對與原子失敗回復。舊格式不因增加解碼器而改寫；原始來源世界不被修改。

### 完成內容與驗收

- 生成物的完整 Entity、JSON recipe metadata、lineage State cells 與版本值，能經 Snapshot 或完整 EventLog 重建，再執行拾取／放下。
- 支援 checkpoint 回退後合法重建、動態物件與 generated player 共存、未完成排程恢復，以及既有 Snapshot 可選欄位的預設值。
- 非法版本、錯誤交易配對、缺 creator binding、重複 live ID 與無法保存的 Entity 資料會拒絕；extension Replay 失敗回復整次操作的記憶體狀態。重播不追加 log、不發布事件，也不重新執行生成器。
- 普通 `WorldRuntime` 先拒絕不支援的 entity log；`EntityTransactionRuntime` 在 delayed Action 執行前重查 actor，且始終保留 Package-backed ID，避免成功成果與還原規則不一致。
- 提供 `examples/entity_lifecycle_demo.py`，以真正編譯的灰冠世界、持久 log 重開及兩次重啟驗證完整流程。

### 實際驗證紀錄

環境為 Windows／Python 3.14.5；命令設定 `PYTHONPATH=src`，停用 bytecode 與 pytest cache。新增 17 個測試方法，另以 subtests 覆蓋不同錯誤資料及合法對照。

1. 全流程第一版完整測試：**378 passed / 3 failed**。三個失敗同屬示範物件 `portable` 欄位放錯，集中修正為既有 Inventory 所讀取的 metadata。
2. 受影響的 persistence／transaction／player-generation 測試：**34 passed**；離線 demo 回 `ok: true`，證明 snapshot 後行動及 durable log 兩次重啟。
3. 修正後完整測試曾為 **383 passed**。獨立審查另重現「排程 actor 被替換」及「已移除 Package ID 被重用」兩個新問題，因此增加對應回歸與一致的前置條件。
4. 最後一批修正後，persistence／transaction／player／Runtime 測試：**95 passed**；審查者獨立複驗新增的兩個案例 **2 passed**，兩項 CHALLENGE 均關閉為 scoped CONCUR。
5. 最終命令 `python -B -m pytest -q -p no:cacheprovider` → **385 passed**（27.11 秒）；`git diff --check` 通過。

本工作包完整路徑與已知必要修正均已驗收。Day 2 的成功不擴張為 Grammar 生成、remove/despawn、Action-child creation、ID allocator 或任意新 Domain 已完成。Replay 需由 host 註冊相容 creator contract；既有 log 不含 module-version receipt，因此仍由 host 固定相容版本。未另宣稱跨平台 CI 或長期大規模效能已量測。

## Day 3 — 2026-09-12：最小 Object Re-entry 閉環

**狀態：COMPLETE（限固定、bounded Grammar 的 Object Re-entry）**

起點 `0e8633f`，分支 `agent/day03-object-reentry`。採 GCT 同批建立 optional Authoring Schema、Compiler／Runtime 載入、固定生成能力、一般文字指令入口、離線對照示範、保存重播與唯讀 VisualRecipe。

`Material → Item → Event/History → 下一次生成`：在固定 Grammar 中讓既有物件／歷史確實改變下一次生成的合法性或性能；VisualRecipe 是同一 state 的唯讀投影，不需要等待完整視覺客戶端。

本日限定固定 Grammar 的 Object Re-entry；不加入材料庫存經濟、Grammar 自我修改、Domain Graph、AI 生成或完整視覺編輯器。詳細契約見 [Object Re-entry v0.1](OBJECT_REENTRY_V0_1.md)。

### 本日交付

- Authoring 的材料／配方／限制先通過版本化 Schema 與 Compiler，產生帶來源 checksum 與內容 hash 的 optional compiled grammar；Runtime 自行重驗，而非只信任編譯成功。
- `craft` 與 `use_tool` 經 ActionIR 和 ModuleContract 執行。生成新物件、父工具磨耗與歷史引用在同一交易提交；失敗不留下成品或消耗工具。
- 成品配方保存 grammar 版本、固定 seed 演算法、實際 seed、材料、父工具當時的 power／condition／depth、State 版本及 history event 引用。
- 讀檔回退後可重建同一配方；持久 log Replay 後可繼續生成。一般 `play`／`serve` 載入有該能力的 Package 時，自選 create-only Runtime；文字 parser 支援 craft／use_tool。
- 提供唯讀 VisualRecipe，以及可執行的 `examples/object_reentry_demo.py`。同材料、seed=23：工具 condition=100 時成品 power=57；真實使用後 condition=75 時 power=49。配方中的 history 引用被保留。

### 驗證紀錄

- 第一輪完整回歸：**400 passed**（28.93 秒）。其後補固定 seed 向量、重算 hash 仍須拒絕非法語義的負例，以及 bool／int 配方型別區別，共新增 18 個測試方法。
- Object Re-entry／Schema 的中途聚焦驗證：**21 passed**（2.10 秒）。同時執行 demo，Snapshot 後再次生成、Replay 後繼續生成皆回 `matched`。
- 真正舊包相容性：在 detached `0e8633f` checkout 用當時 Compiler 編譯 Gray Crown，再交給今日 loader，成功以普通 `WorldRuntime` 載入 10 個既有模組。舊包 SHA-256：`91F91BF47E07B4B44720659284A8DBDC233B16D65DDA2ACEC0FF9BE7182FCAC7`。
- 獨立 reviewer 對 bounded 候選及最後小差異給出 scoped CONCUR；未宣稱他重跑主 AI 的完整 suite。
- 最終 `PYTHONPATH=src python -B -m pytest -q -p no:cacheprovider`：**403 passed**（27.79 秒），Windows／Python 3.14.5。`git diff --check` 通過。
- 固定向量：示範 grammar hash `a867763e56f75a1597ffc3f244f396139794183fef2c17a83a6e72c6e8f0ca94`，make_tool／iron 的 seed 0、7、23、4294967295 對應 bonus 2、1、2、0。忽略 condition 的生成器會被反事實驗收拒絕。

本日完成「物件與其使用歷史影響下一次生成」這個完整閉環，並未將局部工坊等同於完整 RGGG／CRDWS。

## 下一個工作包：CRDWS 靜態 Domain Graph 與能力對應

將既有工坊與 Runtime 能力掛到可編譯、可驗證、可檢視的靜態 Domain Graph，明確區分 Domain 與 TMS／Module。沿用 Canonical Series 的 additive 路線，先完成世界結構與能力對應，不在同一工作包加入 FDCS、多速率或動態 Domain 變更。
