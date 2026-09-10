# Agent 接手規約

本專案是契約優先的參考 MVP。Agent 修改前必須維持以下不變量：

1. Authoring Layer、Compiled Package、Runtime State 不可混為同一真實來源。
2. UI、Intent Parser 與 AI Adapter 不可直接修改 `StateStore`。
3. TMS 模組只能回傳 `StateDelta` 與 `EventIR`，由 Kernel 原子提交。
4. 新模組必須聲明 `ModuleContract`，且能以 Minimal Kernel 進行孤島測試。
5. 跨模組協作使用事件，不直接呼叫他模組的內部方法。
6. Runtime 必須能在無 AI、無網路、無 Web UI 時完成基本世界執行。
7. 新資料欄位需先修改 Authoring Schema／Compiler，再修改 Runtime；不得只在執行期偷加。
8. 任何破壞存檔相容性的修改，都必須增加 migration 與版本檢查。
9. AMK Raw／Clean 是 Runtime Event Log 與 State 的外部證據層，不可冒充或覆蓋世界真實來源。
10. Memory Adapter 只能訂閱 EventIR；預設失敗不得改變已提交的世界行為，且不可持有 StateStore 寫入路徑。
11. Clean Memory 的晉升、衝突、撤銷與檢索必須保存 attribution、evidence、scope、status 與 version；Agent inference 不可靜默升格為 OBS 事實。
12. checkpoint、replica acknowledgement 與 immutable snapshot 是不同狀態；不得把送出上傳當成已備份。
13. `dialogues.json` 是 StateStore 的唯讀投影來源；`dialogue.core` 只能發出 `dialogue.responded` EventIR，不可用對話文字直接寫入任務、貨幣或世界狀態。
14. 有 `transitions` 的任務只能由 `quest.core` 根據已宣告的 EventIR 原子轉移；同一 `from/on/priority` 的分支必須在編譯期拒絕，不能靠來源順序靜默決定世界真相。

建議任務分工：Compiler Agent、Kernel Agent、Module Agent、Test Agent、Reviewer Agent。提出修改與批准修改不可由同一 Agent 同時完成。
15. MCP Adapter 不得持有 `StateStore.commit()` 或 `seed()` 的直接寫入路徑；只讀工具必須以測試證明呼叫前後 state/event/tick/action registry 不變。
16. MCP Session 是外部連線中繼資料，不是 Runtime State；開啟、關閉或遺失 Session 不得產生世界事件。
17. MCP 事件輸出必須先套用 `EventIR.visibility` 與 actor/role 過濾；未知 visibility 採 fail-closed，除非明確是 admin。
18. 官方 MCP SDK 是可選傳輸依賴，核心 Runtime 與 transport-neutral service 必須在未安裝 SDK 時仍可 import、測試與執行。

## 2026-09-10 起的開發節奏

- 使用者要求每天一個可驗收進度；同一工作包可以涵蓋實作、測試、文件與整合，不能把每個小檔案都拆成一次「繼續」。
- 本專案主力模型偏好 GPT-6（目前選用 `gpt-6-astra`）；實際模型以 host 設定為準，不宣稱 Agent 可以自行切換主模型。
- 接手先閱讀 `docs/DEVELOPMENT_PROGRESS_zh-TW.md`，確認日期、工作樹、基線與下一個工作包。每日紀錄區分已驗收成果與未完成依賴；研究問題及未校準工期維持未知。
- 每日節奏本身不建立排程。自動執行的時間與方式由使用者另行指定。
