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

## 下一個工作包：通用實體的保存與 Replay

先以 create-only `EntityDelta` 建立一個普通物件，驗證 Snapshot 與完整 EventLog Replay 重建同一 entity membership、state 與 lineage，並可繼續執行 Action。先用正反例確認目前缺口，再處理所需的 Runtime／版本契約；不在同一工作包加入 Domain Graph 或動態 Grammar。

通過後再安排 `Material → Item → Event/History → 下一次生成` 的最小 Object Re-entry 閉環。VisualRecipe 是同一 state 的唯讀投影，不需要等待完整視覺客戶端。
