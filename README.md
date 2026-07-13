# CompilableWorld Runtime MVP v0.1.0

這是一套零第三方執行依賴的 Python 參考實作。它將 JSON／CSV Authoring Layer 編譯為 Runtime Package，再由 MSSP 模組化世界核心透過終端機或網頁介面執行——兩者共用同一套 Kernel／Action IR／Module Contract，只是不同的 UI Adapter（見「架構邊界」）。

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

開啟 `http://127.0.0.1:8765/`，可看到房間場景、可點擊的出口（含門鎖狀態）、物品拾取／放下／交付按鈕（交付對象下拉選單只列出場景內的角色/生物，不含門或其他非生命實體）、生命值條、貨幣、任務列表即時更新，以及一個保留給任意指令（`attack`／`say`／`unlock` 等）的輸入框。

## 測試

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## 範例世界

- `examples/gray_crown` — 原始參考範例（示範資料）。
- `examples/mingyun_zhiyu_peace_city` — 真實內容切片，改編自 Neo.K 的《命運之欲》小說世界觀（透過既有的 `worlds/mingyun_zhiyu_peace_city/world-ir.yaml`，見 CompilableWorld-Evennia-Prototype 姊妹 repo；世界觀 canon 資料庫本身在 `worlds/mingyun_zhiyu/data/` 已擴充到 16 城/48 具名角色/公理/魔法系統等規模，本切片仍只用了和平之城賤民區這一小塊，其餘 canon 尚待未來擴充），涵蓋全部 8 個模組：移動、對話、上鎖的門（需攜帶鑰匙道具解鎖）、戰鬥、拾取物品、**交付物品給 NPC 以事件驅動完成任務並發放報酬**、任務列表。實際跑過完整流程驗證過。

在 CLI 中依序輸入（以 `examples/mingyun_zhiyu_peace_city` 為例，完成「找份差事」任務）：

```text
n
take item.firewood_bundle
w
give item.firewood_bundle npc.foreman_laotie
quests
status
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

## 已知邊界

- 目前是單程序、單世界實例；沒有帳號、多人網路與分散式鎖。
- Scheduler 支援延遲 Action，但 CLI 尚未暴露複合行為編輯器。
- Quest 模組現在支援兩種事件驅動的完成條件（`deliver:<item>:<target>`、`reach:<room>`）與貨幣報酬，透過 `WorldRuntime.commit_reaction()`（Kernel 新增的事件反應提交路徑，語義與 `_execute()` 相同：只接受 Delta+Event，權限照樣強制檢查）在 EventBus 上被動觸發，不需要玩家額外下指令；未知條件類型一律視為未滿足（fail closed），不會誤判完成。仍未支援的部分：多階段/分支任務、失敗狀態、道具型報酬（只有貨幣，因為 Kernel 目前不支援執行期生成新實體）。
- 世界、區域與場景的初始階層狀態已編入 State Store；跨層事件轉移規則留待 v0.2。
- Intent Parser 是確定性參考實作；AI Adapter 必須輸出同一 `ActionIR` 並接受 Kernel 驗證。
- Module Contract 的寫入範圍已由 Kernel 強制檢查；讀取範圍與 Action authority 的強制隔離留待 v0.2。
- JSON Schema 與 CSV Schema 目前由程式內驗證器實作；v0.2 應外部化為正式 Schema 檔。
- Replay 重放已提交 Delta；跨版本重放仍需 migration registry。
- Web Gateway 是單一 actor、單一瀏覽器分頁假設下的 request/response API（無 WebSocket、無帳號/session），與已知的單程序/單世界限制一致；`/api/action` 與 `/api/state` 共用同一把 lock 序列化存取，避免併發提交造成的版本衝突，但不是為多人設計的。
- （已修復，記錄供參考）CLI 曾在非 UTF-8 系統 locale（例如繁體中文 Windows 的 cp950）下對含中文標點的 `say` 輸入拋出編碼錯誤；`cli.py` 現在會在啟動時強制 stdin/stdout 為 UTF-8。
