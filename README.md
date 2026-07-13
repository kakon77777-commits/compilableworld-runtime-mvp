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
- `examples/mingyun_zhiyu_peace_city` — 真實內容切片，改編自 Neo.K 的《命運之欲》小說世界觀（透過既有的 `worlds/mingyun_zhiyu_peace_city/world-ir.yaml`，見 CompilableWorld-Evennia-Prototype 姊妹 repo；世界觀 canon 資料庫本身在 `worlds/mingyun_zhiyu/data/` 已擴充到 16 城/48 具名角色/公理/魔法系統等規模，本切片仍只用了和平之城賤民區這一小塊，其餘 canon 尚待未來擴充），涵蓋全部 8 個模組：移動、對話、上鎖的門（需攜帶鑰匙道具解鎖）、戰鬥、拾取物品、**交付物品給 NPC 以事件驅動完成任務並發放報酬**、任務列表。實際跑過完整流程驗證過。北境關卡再往北是 `room.north_garrison`（北境軍營），駐守著具名 canon 角色**沃爾坎·鐵壁**（`worlds/mingyun_zhiyu/data/drafts/characters_peace_city_subtop50.csv` 的 No.13，數值取自 `combat_resolution_system.json` 自己的驗算範例，非另行編造）——玩家（新來者，地板值屬性、tier0）與他交手會實際觸發公式判定路徑，親身體驗「突破門檻」機制：命中率被壓到約 0.2%，20 次攻擊全部落空是預期結果，不是 bug。

在 CLI 中依序輸入（以 `examples/mingyun_zhiyu_peace_city` 為例，完成「找份差事」任務，並可繼續北上見識沃爾坎）：

```text
take 臨時身份牌
n
take item.firewood_bundle
w
give item.firewood_bundle npc.foreman_laotie
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

## 已知邊界

- 目前是單程序、單世界實例；沒有帳號、多人網路與分散式鎖。
- Scheduler 支援延遲 Action，但 CLI 尚未暴露複合行為編輯器。
- 房間／NPC 描述文字是靜態的，不會隨世界狀態變化（例如怪物死亡後場景描述不會更新）；已用一個較輕量的手段部分緩解——`visible_entities` 現在會標示實體是否存活（終端機顯示「（已死亡）」，網頁介面同步），但描述本身的條件式文字/對話狀態感知仍是尚未實作的功能，不是這次修的 bug。
- Quest 模組現在支援兩種事件驅動的完成條件（`deliver:<item>:<target>`、`reach:<room>`）與貨幣報酬，透過 `WorldRuntime.commit_reaction()`（Kernel 新增的事件反應提交路徑，語義與 `_execute()` 相同：只接受 Delta+Event，權限照樣強制檢查）在 EventBus 上被動觸發，不需要玩家額外下指令；未知條件類型一律視為未滿足（fail closed），不會誤判完成。仍未支援的部分：多階段/分支任務、失敗狀態、道具型報酬（只有貨幣，因為 Kernel 目前不支援執行期生成新實體）。
- 世界、區域與場景的初始階層狀態已編入 State Store；跨層事件轉移規則留待 v0.2。
- Intent Parser 是確定性參考實作；AI Adapter 必須輸出同一 `ActionIR` 並接受 Kernel 驗證。
- Module Contract 的寫入範圍已由 Kernel 強制檢查；讀取範圍與 Action authority 的強制隔離留待 v0.2。
- JSON Schema 與 CSV Schema 目前由程式內驗證器實作；v0.2 應外部化為正式 Schema 檔。
- Replay 重放已提交 Delta；跨版本重放仍需 migration registry。
- 戰鬥有兩條判定路徑，同一場戰鬥不會混用：(1) **簡易路徑**——命中率 85%、傷害區間 3-7、`combatant` component 存活反擊機率 75%（區間 1-3），取材自對真實 LPC MUD（mhsj）戰鬥系統的研究，見 `docs/whitepapers/`；(2) **公式路徑**——當雙方都在 `entities.csv` 填了完整五維屬性（`str/con/mag/agi/dex` + 選填 `phase_tier`）時自動啟用，直接還原 `worlds/mingyun_zhiyu/data/drafts/combat_resolution_system.json`（Neo 已審閱核准）的比率制命中/傷害/突破門檻公式**與交鋒（Exchange）先攻回合制**——一次 `attack` 指令＝一次交鋒，`IV=AGI+0.5×DEX` 決定雙方各自的行動次數（`clamp(round(IV_己方/IV_對方),1,4)`），較快一方的行動全部先解算完才輪到較慢一方（來源文件是敘事上的交錯描寫，這裡簡化成「先攻方全部行動完再輪下一方」，非逐拍交錯，有明確記錄不是隱藏簡化）。見 `src/compilableworld/combat_formulas.py`，`tests/test_combat_formulas.py` 用該文件自己的 worked example（露芙緹雅 vs 格洛森、IV比值3.2→3次行動）逐位數比對回歸測試。`examples/mingyun_zhiyu_peace_city` 的 `player.newcomer`（地板值屬性，tier0）與 `npc.woerkan`（真實 canon 數值，tier1）雙方都已授權屬性，實際觸發公式路徑；`creature.sewer_rat`／`npc.guard` 等舊有戰鬥實體刻意留在簡易路徑——公式常數（HP=CON×8、傷害×0.1縮放）是為數百點屬性的正式 canon 角色校準的，硬套在地板值內容上會異常緩慢/肉質過厚（實際算過，不是猜測）。五維屬性欄位為全有全無（部分填寫會編譯失敗），且與舊版 `health` 欄位互斥（HP 改由 CON 推導）。
- 規則魔法施法系統（同一份 `combat_resolution_system.json` 的 `rule_magic_casting_system`）已實作 MP/FP 資源池（由 MAG/DEX 在編譯期自動推導，五維屬性齊全的實體都會有）與 `cast <法術名>` 指令，目前接了兩個法術：`護盾術`（5 符號，MP40/FP25，temp_HP=施法者MAG×2，優先於真實生命值承受傷害，且與其他狀態一樣持續 3 次交鋒——耗盡或到期兩者先到者為準）、`疾風步`（3 符號，MP24/FP15，IV×1.5 持續 3 次交鋒；symbol_count=3 是本專案自己從 `combo_home` 標籤數推斷的，來源文件沒有給這個法術的具體數字，跟 `護盾術` 是文件自己給的範例不同）。異常狀態現在是一個真正通用、會隨交鋒衰減的機制（`combat.status_effects`，見 `combat_formulas.py` 的 `refresh_status`／`decay_status_effects`），不是只為了護盾寫死的一次性欄位——`疾風步` 直接證明這點：它改的是先攻回合制的行動次數，不是傷害或血量。**刻意未實作**：多交鋒引導詠唱（`cast_time_exchanges>1` 的高階法術，需要在交鋒之間插入「引導中斷判定」，目前交鋒已實作但引導/中斷邏輯還沒有——本輪也刻意簡化成「施法本身不消耗交鋒」，跟來源文件嚴格定義有落差，已記錄）；完整的異常狀態框架其餘 9 種（麻痺/破綻/凍傷/束縛/靜默等，目前只做了 shield_buff／haste_疾風 兩種，通用的衰減/刷新機制已就位，加新狀態的邊際成本應該不高）；近戰以外招式（`ranged_precision_physical`／`mental_spiritual` 這兩種攻擊類型公式已在來源文件定義好，尚未接線）。這些是該檔案裡份量最大的剩餘部分，留待未來階段。
- Web Gateway 是單一 actor、單一瀏覽器分頁假設下的 request/response API（無 WebSocket、無帳號/session），與已知的單程序/單世界限制一致；`/api/action` 與 `/api/state` 共用同一把 lock 序列化存取，避免併發提交造成的版本衝突，但不是為多人設計的。
- （已修復，記錄供參考）CLI 曾在非 UTF-8 系統 locale（例如繁體中文 Windows 的 cp950）下對含中文標點的 `say` 輸入拋出編碼錯誤；`cli.py` 現在會在啟動時強制 stdin/stdout 為 UTF-8。
- （已修復，源自一次真實的 AI 玩家試玩）指令目標現在可以用場景內可見的顯示名稱（例如「老鐵」）指定，不再強制要求內部 ID（`npc.foreman_laotie`）——`DeterministicIntentParser` 會在目前房間與玩家物品欄中做名稱解析，找不到或有歧義時一律不猜測、原樣傳給下層模組，讓玩家看到正常的「找不到」訊息，不會誤觸錯的目標。同一輪試玩也發現 `give` 沒有保護機制、可以把仍在使用中的鑰匙道具送給不相關 NPC 且無法復原——現在會在該鑰匙鎖著的門還沒開之前擋下交付。另外修正：裸方向詞（`north`）現在可直接使用；`unlock` 對非門實體會給出正確訊息而非誤導的「門沒有上鎖」；戰鬥現在有反擊傷害與獨立的擊殺訊息。
