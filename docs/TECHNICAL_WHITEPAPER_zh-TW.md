---
title: "CompilableWorld Runtime v0.1：MSSP 模組化可編譯世界執行引擎技術白皮書"
subtitle: "從 Evennia 參考實作、世界資料編譯與階層狀態機，到可執行、可重播、可由 Agent 接手的非網頁型 Runtime"
author: "Neo.K / EVEMISSLAB"
version: "v0.1"
status: "技術白皮書暨參考 MVP 實作基線"
date: "2026-07-13"
language: "zh-TW"
keywords:
  - CompilableWorld
  - MSSP
  - Modular World Runtime
  - World IR
  - Action IR
  - Event IR
  - State Delta
  - Event Sourcing
  - MUD
  - AI Agent
  - Evennia
---

# CompilableWorld Runtime v0.1：MSSP 模組化可編譯世界執行引擎技術白皮書

## 摘要

本白皮書提出並實作一套非網頁型的 CompilableWorld Runtime 參考架構。系統以 MUD 終端機作為第一個世界操作介面，以 JSON、CSV 與 Manifest 作為人類—AI 共編的 Authoring Layer，以可驗證 Runtime Package 作為編譯邊界，以最小 World Kernel、MSSP 機制模組、Action IR、State Delta、Event IR、Snapshot 與 Replay 作為執行核心。

本文的核心決策不是「重寫一個新的傳統 MUD」，而是把 MUD 降為可編譯世界的第一個低成本投影介面。Evennia 仍有參考實作、早期原型、相容輸出與多人協定研究價值，但不再被指定為世界本體、唯一資料模型或 Canonical Runtime。

本系統將世界定義、世界執行與世界呈現明確分離：

$$
A_W
\xrightarrow{\mathcal{N}}
W_{\mathrm{IR}}
\xrightarrow{\mathcal{C}}
P_R
\xrightarrow{\mathcal{L}}
W_t
\xrightarrow{\mathcal{V}}
U_t
$$

其中：

- $A_W$ 是 JSON、CSV、Manifest、EML 與其他來源構成的 Authoring Layer；
- $W_{\mathrm{IR}}$ 是正規化、已解析引用、已通過驗證的世界中間表示；
- $P_R$ 是具版本與雜湊的 Runtime Package；
- $W_t$ 是時間 $t$ 的可執行世界狀態；
- $U_t$ 是終端機、Web、桌面或 Agent 所看到的世界投影。

AI 在此架構中不是世界規則的最終裁決者，而是來源解析器、世界編譯協作者、Action IR 產生器、局部敘事生成器、測試者與 Patch 提案者。所有具世界效力的修改，都必須經由確定性的驗證、權限與提交邊界。

本白皮書同時附帶 Python 3.11+ 的零第三方執行依賴 MVP。它可直接編譯範例世界、啟動終端機、執行移動、門鎖、物品、生命、戰鬥、對話與任務投影，並驗證事件紀錄、排程、Snapshot 與 Replay。Python 版本的目的，是先凍結語言無關契約與行為語義；高併發 Kernel 可在後續依相同契約移植至 Rust。

---

# 第一章　文件基線與整合原則

## 1.1 主文件優先級

本白皮書以《從 Evennia 參考實作到 MSSP 模組化世界執行引擎：CompilableWorld Runtime 的重構原則 v0.1》為最高優先級架構基線，並吸收下列文件的後續擴張：

1. MSSP-Scale Skill 的 FMS、SMS、TMS、SCL、DMS、Router 與孤島測試；
2. MUD 世界工程 MSSP Skill System 的多 Agent 分權、驗證閉環與發布治理；
3. 可編譯世界平台的 World IR、AI 玩家、自動測試與跨 Runtime 思想；
4. JSON／CSV／Manifest 前置資料層的唯一真實來源、版本與可重現編譯；
5. 超大型階層式有限狀態世界的 Action IR、Event IR、複合行為與事件轉導；
6. Novel-to-MUD 的離線大型改編、World Seed Package、Canon 分層與 Runtime 局部 AI。

英文翻譯版只用於術語核對，不被視為新增架構需求，避免相同概念在規格中被重複計權。

## 1.2 整合後的五項不可逆決策

第一，Evennia 從核心依賴降為 Reference Implementation、Prototype Target 與 Compatibility Adapter。

第二，Authoring Layer、World IR、Runtime Package 與 Runtime State 必須分離，且在不同生命週期各自擁有唯一真實來源。

第三，Kernel 只保留所有世界都需要的最小執行能力；戰鬥、任務、魔法、經濟與 AI NPC 等都屬於可替換機制模組。

第四，任何模組、AI、UI 或 Gateway 都不能直接修改世界狀態；它們只能提交 Action、Delta 或 Patch，由 Kernel 驗證與提交。

第五，MUD 是第一個介面，不是最終邊界。同一世界狀態未來可以投影為終端機、Web、桌面、策略模擬、互動小說或 Agent 社會。

---

# 第二章　問題定義：真正要建造的是世界執行器

傳統 MUD 框架通常把帳號、連線、指令、物件、房間、腳本、資料庫與呈現綁在同一套框架抽象中。這對快速建立一款 MUD 很有效；但當目標變成「從小說與世界觀編譯出長期演化世界」，原有抽象就會出現錯位。

CompilableWorld 所需處理的不是單一遊戲規則，而是：

- 多來源世界資料；
- Canon、推論、遊戲化改編與 Runtime 生成的來源差異；
- 世界級、區域級、場景級、實體級、系統級與行為級狀態；
- 多步驟、延遲、可中斷與並行行為；
- 跨模組事件轉導；
- AI 與 Agent 的權限邊界；
- 世界版本、存檔版本、遷移、分支、重播與審計；
- 多種 Runtime 與多種 UI 的等價投影。

因此系統的正式目標應寫成：

> 將異質世界來源轉換為可驗證世界定義，再由一個與 UI、AI 與特定遊戲玩法解耦的 Runtime，持續執行可追蹤的世界狀態轉移。

---

# 第三章　總體架構

## 3.1 六層 Runtime

完整 Runtime 定義為：

$$
\mathcal{R}_W=(K,M,G,V,A,D)
$$

其中：

- $K$：World Kernel；
- $M$：MSSP Mechanism Modules；
- $G$：Gateway and Protocol；
- $V$：View and Projection；
- $A$：AI and Agent Layer；
- $D$：Diagnostics, Observability and Operations。

資料與執行流程為：

```text
Novel / World Source / Human Editing
                ↓
Offline Adaptation + Authoring Layer
                ↓
JSON / CSV / EML / Manifest
                ↓
Normalize → Validate → Resolve → Compile
                ↓
Runtime Package / World IR subset
                ↓
World Kernel + MSSP Modules
                ↓
State Delta → Atomic Commit → Event IR
                ↓
Projection / Terminal / Agent Observation
```

## 3.2 三種真實來源

同一份資料不能在 CSV、資料庫、AI 記憶與 Runtime Object 中同時可被任意修改。正確規則是：

| 生命週期 | 唯一真實來源 | 禁止事項 |
|---|---|---|
| 設計期 | Authoring Layer | 直接把 Runtime DB 當世界定義編輯器 |
| 編譯期 | Validated World IR | 讓編譯器掃描並猜測未列入 Manifest 的檔案 |
| 執行期 | Runtime State／Event History | Runtime 反向覆蓋 Seed 或原作資料 |
| 更新期 | 新版 Authoring Layer＋Migration | 直接對正式世界做無版本 Patch |

此分離可寫成：

$$
A_W \neq W_{\mathrm{IR}} \neq R_W
$$

三者雖不相同，但必須存在有版本、可重現的轉換函數。

---

# 第四章　Authoring Layer 與 World Seed Package

## 4.1 格式分工

JSON 適合保存巢狀規則、任務、世界公理、時間線、關係、Manifest 與來源資訊。CSV 適合房間、出口、角色、物品、平衡參數、翻譯與大量同型資料。EML 可在後續成為高密度語義與規則前端，但不取代 JSON／CSV 的交換與批次維護價值。

Manifest 是唯一編譯入口，至少應聲明：

- 世界、Schema、Compiler 與目標 Runtime 版本；
- namespace；
- 所有來源檔案；
- 模組需求；
- 嚴格模式與警告政策；
- 雜湊或簽章；
- 來源與人工審查狀態。

## 4.2 Canon 分層

小說改編不可把 AI 推論偽裝為原作事實。每筆重要資料應至少能標記：

```text
explicit_canon
inferred_canon
gameplay_adaptation
runtime_generation
human_override
```

同時必須區分角色信念與世界事實：

$$
B_{\mathrm{character}} \neq F_{\mathrm{world}}
$$

## 4.3 離線與執行期 AI 分離

完整小說、年表與世界設定應在離線改編階段處理，產生可索引、可審查、可增量更新的 World Seed Package。Runtime AI 只取得當前區域、角色、任務、規則與近期事件所構成的局部上下文包。

這能同時降低 Token 成本、延遲與設定漂移，並讓每次重大世界修改形成可比較 Patch。

---

# 第五章　World Kernel 的最小責任

Kernel 不回答「這個遊戲是否好玩」，只回答「這次世界轉移是否有效、獲授權、無衝突、可提交與可重播」。其最低構成為：

1. Entity Registry；
2. State Store；
3. Action Runtime；
4. Transition Engine；
5. Event Bus；
6. Scheduler；
7. Permission Engine；
8. Module Runtime；
9. Persistence；
10. Snapshot／Replay；
11. Transaction／Delta Commit；
12. Protocol Gateway 契約。

世界在時間 $t$ 的執行狀態可寫成：

$$
W_t=(E,S,Q,H,C)
$$

其中 $E$ 是實體集合，$S$ 是狀態儲存，$Q$ 是待執行行為與事件佇列，$H$ 是事件歷史，$C$ 是已載入契約與世界上下文。

Kernel 不需要理解「狼人」的敘事意義；它只需要知道該實體有哪些 component、目前狀態、可引用 ID 與哪些模組可以對其提出何種 Delta。

---

# 第六章　階層式有限狀態世界

本系統不是建立一顆包含所有房間、NPC、天氣、任務與戰鬥狀態的巨大 FSM，而是建立可組合的狀態機群：

$$
\mathcal{H}
=
\mathcal{H}_{world}
\oplus
\mathcal{H}_{region}
\oplus
\mathcal{H}_{scene}
\oplus
\mathcal{H}_{entity}
\oplus
\mathcal{H}_{system}
\oplus
\mathcal{H}_{action}
$$

不同尺度的狀態機不直接相互竄改內部狀態，而是以 Event IR 與受權限控制的 Delta 產生轉導。例如：

```text
combat.damage_applied
        ↓
health.current 改變
        ↓
combat.actor_defeated
        ↓
quest / faction / narrative / UI 各自投影
```

這使世界可增加新模組，而不必把舊模組改寫成知道所有未來系統的中央控制器。

---

# 第七章　Action IR 與複合行為

## 7.1 Action 不是指令字串

自然語言、終端機命令、Web 按鈕與 Agent 決策，都應轉換成同一 Action IR：

```json
{
  "action_id": "action_...",
  "actor_id": "player.neo",
  "verb": "unlock",
  "target_id": "door.old_vault",
  "args": {},
  "authority": "player",
  "correlation_id": "corr_..."
}
```

Action 生命週期為：

```text
Proposed → Parsed → Validated → Scheduled → Executing
                                      ↓
                         Completed / Failed / Interrupted
```

## 7.2 AI 的正確位置

對高複雜度自然語言，AI 可執行：

$$
T_{\mathrm{player}}
\xrightarrow{\mathcal{P}_{AI}}
A_{\mathrm{candidate}}
$$

但候選行為仍須經：

$$
A_{\mathrm{candidate}}
\xrightarrow{\mathcal{V}_{det}}
A_{\mathrm{valid}}
\xrightarrow{\mathcal{T}}
(\Delta S,E)
$$

AI 可以產生「嘗試無聲開門」的結構化步驟，卻不能直接宣稱成功、直接把門改成已開，或繞過鑰匙、位置與權限檢查。

## 7.3 複合行為

完整 Action Graph 最終應允許表達：

- sequence；
- parallel；
- wait；
- condition；
- retry；
- timeout；
- cancellation；
- compensation。

目前參考 Runtime 已實作固定 sequence phases、bounded wait duration、sticky priority-selected conditional child branch、implicit linear rejoin、非遞迴 primitive child Action sequence、phase-entry condition、fixed-interval retry/deadline 與 cancellation/interruption；parallel child Action、nested branch、任意／遞迴 phase graph、explicit join 與 compensation 仍未實作。所有已落地部分仍由 Action 狀態、Scheduler、`action.branch_selected`／其他 EventIR、Snapshot 與 Replay 保存，不繞過 StateDelta 提交契約。

---

# 第八章　Transition、Delta 與原子提交

每個機制模組實作的不是任意狀態修改，而是轉移函數：

$$
r_m:(S_t,A,C,P_m)\rightarrow(\Delta S,E,R)
$$

其中 $P_m$ 是模組契約與權限，$R$ 是接受或拒絕結果。

Kernel 僅在下列條件同時成立時提交：

$$
\mathrm{Commit}(\Delta S)=1
\iff
V_{schema}
\land
V_{permission}
\land
V_{reference}
\land
V_{version}
\land
V_{conflict}
$$

同一次 Action 產生的多個 Delta 必須原子處理。如果第二個 Delta 越權或版本衝突，第一個 Delta 也不能留下部分修改。

MVP 支援 `set`、`add`、`subtract`、`append` 與 `remove` 操作，並保留 `expected_version` 作為樂觀併發控制入口。

---

# 第九章　Event IR、事件轉導與重播

Event 是跨模組協作介面，而不是除錯用字串。Event IR 至少包含：

- Event Type；
- Source／Target；
- Causation ID；
- Correlation ID；
- Tick／Timestamp；
- Payload；
- Visibility；
- Authority；
- Version。

每次成功提交都產生 `state.committed` 審計事件，並保存結構化的 `owner`、`namespace`、`key`、`value` 與 `version`。這使 Runtime 能從 Snapshot 加後續事件恢復狀態，也讓測試 Agent 能重現錯誤。

理想狀態重建為：

$$
S_t
=
\operatorname{Fold}
\left(
S_{snapshot},
E_{snapshot+1:t}
\right)
$$

事件不可任意刪除或被敘事層改寫。敘事文字只是事件的投影，不能反過來成為規則結果。

---

# 第十章　MSSP 模組契約

## 10.1 SMS 與 TMS

SMS 保存不可缺少的核心能力，例如 entity、state、action、event、permission、persistence 與 scheduling。TMS 保存可插拔玩法，例如 movement、door、inventory、combat、quest、economy、law、magic、AI NPC 與 AI GM。

MVP 為了保持單一套件易於執行，將內建模組放在同一 Python package；但它們在語義上仍是 TMS，並透過 Module Contract 註冊，不屬於 Kernel 內部規則。

## 10.2 最小契約

每個模組必須聲明：

- `module_id`、版本與 MSSP layer；
- 需要的 Kernel 能力；
- 提供的 Action 與 Event；
- 可讀狀態；
- 可寫狀態；
- 測試與 UI projection。

模組不得直接操作資料庫或另一模組的私有物件。跨模組依賴若形成網狀隱藏呼叫，便失去 MSSP 的意義。

## 10.3 孤島測試

每個 TMS 至少要能在下列組合測試：

```text
Minimal Kernel
+ Mock Entity
+ Mock State
+ Mock Event Bus
+ Target Module
```

如果 Combat 測試必須啟動 Quest、Economy、AI GM 與完整 UI，表示模組契約或事件邊界已失效。

---

# 第十一章　Gateway、Projection 與 UI 分離

Gateway 的工作是把不同輸入轉成 Action IR。Projection 的工作是把世界狀態與事件轉成使用者可見模型。兩者都不執行遊戲規則。

$$
U_i=\Pi_i(W_t,E_{\leq t},P_i)
$$

其中 $\Pi_i$ 是第 $i$ 種介面的投影函數，$P_i$ 是該觀察者權限。

因此終端機、Web、桌面、管理介面與 Agent Observation 可以共享同一 Runtime。MVP 只實作 Terminal Gateway，因為它最適合在低成本下驗證世界狀態、Action IR 與事件歷史；它不是把產品永久限制為文字介面。

---

# 第十二章　AI 與多 Agent 治理

## 12.1 角色分權

建議角色包括：

- World Builder Agent；
- Rule Agent；
- Programmer Agent；
- GM Agent；
- NPC Agent；
- Player Agent；
- Test Agent；
- Reviewer Agent；
- Release Agent。

提出 Patch、實作 Patch、審查 Patch 與發布 Patch 不應全部由同一 Agent 自行完成。系統需要保留人類可見的 Diff、測試結果、風險等級、相容性與回滾方式。

## 12.2 AI 不可成為 Kernel 必需品

Kernel 必須在無 AI Provider、無網路與無自然語言模型時仍能：

- 載入世界；
- 執行確定性 Action；
- 提交 Delta；
- 產生 Event；
- 儲存 Snapshot；
- 重播狀態。

這不否定 AI 的價值，而是讓 AI 成為可替換能力，而非世界一致性的單點失效來源。

## 12.3 不可信輸入

小說、玩家文字與 AI 輸出都應視為不可信資料。小說中的「忽略規則」「取得管理員權限」可能只是台詞，也可能構成 Prompt Injection。任何來源文本都不能直接變成系統指令或部署權限。

---

# 第十三章　參考 MVP 的實際結構

```text
compilableworld-runtime-mvp/
├── pyproject.toml
├── README.md
├── AGENTS.md
├── TECHNICAL_WHITEPAPER_zh-TW.md
├── src/compilableworld/
│   ├── compiler.py
│   ├── models.py
│   ├── kernel.py
│   ├── modules.py
│   ├── gateway.py
│   └── cli.py
├── examples/gray_crown/
│   ├── manifest.json
│   ├── world.json
│   ├── quests.json
│   └── data/*.csv
└── tests/test_runtime.py
```

## 13.1 編譯器

編譯器目前實作：

- Manifest 唯一入口；
- 防止來源路徑越界；
- JSON／CSV 語法讀取；
- 必填欄位；
- ID 格式與唯一性；
- 跨表引用；
- 出生點與房間可達性；
- 模組鎖定；
- 來源 SHA-256；
- 可重現的 Runtime Package 與 Build Report。

## 13.2 Runtime

Runtime 目前實作：

- Entity Registry；
- Versioned State Store；
- Action IR 生命週期；
- Module Contract；
- Delta 權限與原子提交；
- Event Bus 與 JSONL Event Log；
- Tick Scheduler；
- Snapshot；
- 已提交 Delta 的 Replay；
- DMS diagnostics。

## 13.3 第一批 TMS

| 模組 | Action | 主要能力 |
|---|---|---|
| `room.core` | `look` | 場景觀察與可見實體投影 |
| `movement.core` | `move` | 出口、方向、門狀態與位置轉移 |
| `door.core` | `open`, `unlock` | 鑰匙、上鎖與開門狀態 |
| `inventory.core` | `take`, `drop`, `inventory` | 物品位置與持有者轉移 |
| `health.core` | `status` | 生命狀態投影 |
| `combat.basic` | `attack` | 確定性傷害與 defeated Event |
| `dialogue.core` | `say` | 對話事件，不改寫規則 |
| `quest.core` | `quests` | 任務狀態投影基線 |

---

# 第十四章　執行範例

## 14.1 編譯

```bash
PYTHONPATH=src python3 -m compilableworld validate examples/gray_crown
PYTHONPATH=src python3 -m compilableworld compile examples/gray_crown --out build/gray_crown
```

## 14.2 啟動

```bash
PYTHONPATH=src python3 -m compilableworld play build/gray_crown/world.package.json
```

## 14.3 驗證世界閉環

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

這一流程同時驗證物品、移動、門鎖、狀態提交、事件產生、場景投影與 Snapshot。

---

# 第十五章　測試、DMS 與完成證明

產生輸出不等於完成。每項 Agent 工作都必須附帶機器可驗證證據與人類可讀狀態。

MVP 的七項自動測試涵蓋：

1. 合法範例世界驗證；
2. 世界／區域／場景階層狀態與任務初始狀態編譯；
3. Manifest 來源路徑越界拒絕；
4. Delta 越權時整批不提交；
5. 移動、物品、門鎖與事件重播閉環；
6. Snapshot 儲存與載入；
7. Scheduler 延遲執行。

DMS 至少輸出世界版本、Tick、實體數、狀態數、模組版本、待執行 Action、事件數、成功與失敗 Action 數。

後續應加入：

- 地圖覆蓋率；
- Action 與事件覆蓋率；
- 任務分支覆蓋率；
- Replay Integrity；
- Scheduler Lag；
- State Conflict Rate；
- Migration Compatibility；
- AI Token、延遲與成本；
- 玩家可見狀態與權限洩漏測試。

---

# 第十六章　安全、權限與一致性

## 16.1 權限不是提示文字

「請勿修改管理員狀態」不是安全機制。模組的可寫 namespace 必須由 Kernel 機械驗證；AI 的 authority 與玩家的 visibility 也應在資料契約中表示。

## 16.2 編譯安全

Manifest 不可允許來源使用 `../` 越界讀取。編譯器不應任意掃描整個專案後自動載入未知檔。來源雜湊、Compiler 版本與 Build Report 是可重現建置的最低要求。

## 16.3 Runtime 安全

任何模組都不可：

- 直接連線並修改外部資料庫；
- 繞過 State Store；
- 刪除 Event Log；
- 動態執行未審查 AI 程式碼；
- 同時提出、批准並發布高風險 Patch。

未來原生模組與第三方模組需要能力式權限、資源限制、簽章、版本鎖與沙盒。

---

# 第十七章　併發、衝突與長期行為

MVP 為單程序參考 Runtime，但已透過版本化 State Cell 與 `expected_version` 保留樂觀併發控制語義。正式多人版應將一次提交視為：

$$
T=(R,W,V,O)
$$

其中 $R$ 是讀集合，$W$ 是寫集合，$V$ 是預期版本，$O$ 是衝突政策。

衝突政策可包含：

- reject；
- retry；
- priority；
- merge；
- compensate；
- serialize-by-entity。

複合行為自身也需要狀態機。長時間開鎖、施法、製作與移動應能被中斷、取消、補償或因前置條件失效而失敗，而不是在輸入瞬間把最終結果寫入世界。

---

# 第十八章　Python 參考實作與 Rust Runtime 的關係

本 MVP 選擇 Python，不是宣告最終高併發核心必須是 Python，而是因為當前階段最重要的是快速凍結：

- Runtime Package；
- Action IR；
- State Delta；
- Event IR；
- Module Contract；
- Snapshot／Replay 語義；
- 測試案例。

Rust 重寫應採契約相容，而非逐行翻譯。建議路徑為：

1. 先為所有 IR 建立版本化 JSON Schema；
2. 建立 Python／Rust Golden Fixtures；
3. 讓兩個 Runtime 對同一 Action Sequence 產生等價 State／Event；
4. 再把 State Store、Event Bus、Scheduler、Transaction 與 Networking 移入 Rust；
5. 保留 Python 作為 Compiler、AI Adapter、MCP、資料管線與快速模組原型層。

跨語言等價條件可寫成：

$$
\operatorname{Obs}
\left(
R_{py}(P,A_{1:n})
\right)
=
\operatorname{Obs}
\left(
R_{rs}(P,A_{1:n})
\right)
$$

其中 `Obs` 比較的是可觀察狀態與事件，而不是記憶體配置或內部類別名稱。

---

# 第十九章　版本路線

## v0.1：本次交付

- JSON／CSV／Manifest 編譯；
- 單機 Runtime；
- 八個基礎 TMS；
- Terminal Gateway；
- Action／Delta／Event 契約；
- Scheduler；
- Snapshot／Replay；
- 測試與 Agent 接手規約。

## v0.2：契約外部化

- 正式 JSON Schema 與 CSV Schema；
- Runtime Package 拆檔與 `modules.lock`；
- 任務狀態機與事件訂閱；
- 複合 Action Graph；
- Migration Registry；
- Patch／Diff／Rollback；
- 更完整的 Permission、Visibility 與 Authority。

## v0.3：Agent 與自動測試

- AI Intent Adapter；
- AI Player；
- Test／Reviewer／Release Agent 分權；
- 路徑、任務、經濟與惡意行為測試；
- Human-Visible DMS 報告；
- 局部 Runtime Context Router。

## v0.4：Rust Kernel 與多人 Gateway

- Rust State Store、Event Bus、Scheduler 與 Transaction；
- Python Compiler／AI Tooling；
- 多世界實例；
- 帳號、Session 與多人連線；
- Evennia Import／Export Adapter；
- WebSocket／HTTP 僅作 Gateway，不改變 Kernel 規則。

## v1.0：可編譯共同世界

- 世界分支與合併；
- 公開／私人世界；
- 長期持久化；
- 跨版本存檔遷移；
- 世界分享與模組生態；
- 多介面等價投影；
- 受控 AI GM 與局部世界 Patch。

---

# 第二十章　Agent 接手優先序

下一批 Agent 不應同時大改全部層級。建議依下列順序工作：

1. **Schema Agent**：把目前程式內驗證規則外部化，凍結 v0.1 IR Schema；
2. **Compiler Agent**：加入多檔來源、錯誤隔離、來源定位與 deterministic build；
3. **Kernel Agent**：補齊 transaction、conflict policy、action cancellation 與 migration hook；
4. **Module Agent**：先完成 Quest FSM 與事件訂閱，再擴張經濟、法規與魔法；
5. **Test Agent**：建立 Golden Action Sequence、Property Test 與 Replay Integrity；
6. **Reviewer Agent**：檢查 Kernel／Module 邊界與隱藏耦合；
7. **Rust Port Agent**：只在契約與 Golden Fixtures 穩定後開始移植。

每個變更都應回答：

- 改的是 Authoring、IR、Runtime、Module、Gateway 還是 Projection？
- 是否改變存檔或事件相容性？
- 是否需要 Schema／Migration？
- 是否新增權限？
- 是否能孤島測試？
- 是否保留無 AI 執行能力？
- 是否有可重播的完成證明？

---

# 第二十一章　已知限制與非目標

本版有意不完成：

- Web UI；
- 生產級多人網路；
- 分散式一致性；
- 讀取 namespace 與 Action authority 的完整強制隔離；
- 動態載入未信任原生模組；
- 完整自然語言 AI Parser；
- 自動修改正式世界；
- 完整 Novel-to-MUD 抽取管線；
- 跨版本 Migration；
- 完整 Quest、Economy、Law、Magic 與 AI NPC。

這些不是被否定，而是被放到正確邊界與版本。v0.1 的目的，是先證明一個世界可以從 Authoring Layer 被編譯，經由最小 Kernel 與可替換 TMS 執行，並留下可測、可存、可重播的狀態歷史。

---

# 第二十二章　結論

CompilableWorld Runtime 的真正價值，不是重新製作一套具更多指令的 MUD，而是建立「敘事世界成為可執行世界」的中介層與執行邊界。

其完整命題為：

$$
\mathrm{CompilableWorld}
=
\mathrm{Source\ Governance}
+
\mathrm{World\ Compiler}
+
\mathrm{Runtime\ Contracts}
+
\mathrm{Modular\ Mechanisms}
+
\mathrm{Event\ History}
+
\mathrm{Controlled\ AI}
$$

Evennia 提供了重要的早期參考，但不應再定義世界的上限。MUD 提供了第一個高語義、低圖像成本的入口，但不應再等同於整個引擎。AI 提供了自然語言理解、改編與測試能力，但不應再等同於最終裁決權。

本次 v0.1 已把核心主張落為可執行原始碼：世界可由 Manifest 進入編譯器；Action 可由 Gateway 進入 Kernel；模組只能提出 Delta 與 Event；狀態修改可被原子提交；歷史可被保存與重播；整個基本世界在沒有 Web 與 AI 的情況下仍能運行。

這不是終局，而是後續 Agent、Rust Kernel、AI 玩家、局部世界生成與多介面共同世界可以共同依賴的第一個可編譯基線。

---

## 附錄 A　v0.1 驗收清單

- [x] Evennia 不作 Canonical Runtime
- [x] Authoring Layer 與 Runtime State 分離
- [x] Manifest 是唯一編譯入口
- [x] 來源路徑不可越界
- [x] ID 與跨表引用驗證
- [x] Runtime Package 具版本與來源雜湊
- [x] Entity Registry
- [x] Versioned State Store
- [x] Action IR 與生命週期
- [x] 模組回傳 Delta／Event
- [x] Delta 原子提交與 namespace 權限
- [x] Event Bus 與 Event Log
- [x] Tick Scheduler
- [x] Snapshot
- [x] Replay
- [x] Terminal Gateway
- [x] Runtime 無 AI 仍可運作
- [x] 基礎模組與範例世界
- [x] 自動測試與 Agent 接手規約
- [ ] 外部化 IR Schema
- [ ] 複合 Action Graph
- [ ] Quest Event FSM
- [ ] Migration Registry
- [ ] Rust Kernel
- [ ] 多人 Gateway

## 附錄 B　最小反模式清單

- Kernel 內建所有玩法；
- UI 直接修改狀態；
- AI 直接寫資料庫；
- Runtime 反向覆蓋 Seed；
- 模組直接呼叫他模組內部方法；
- 沒有 Manifest 而掃描整個資料夾；
- 把角色信念當世界公理；
- 把敘事文字當規則結果；
- Action 瞬間跳到最終狀態而無生命週期；
- Event 只有文字，沒有 causation／correlation；
- Agent 自己提案、實作、審查並發布；
- 沒有 Snapshot、Replay、Migration 卻宣稱支援長期世界。
