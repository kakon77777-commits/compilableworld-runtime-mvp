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
