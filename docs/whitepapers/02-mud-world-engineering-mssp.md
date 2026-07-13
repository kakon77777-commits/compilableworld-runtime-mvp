---
title: "MUD 世界工程 MSSP Skill System：可編譯世界、AI 協作與模組化 Agent 能力架構"
subtitle: "從小說輸入、世界建模、規則驗證到 AI GM、AI 玩家與多引擎輸出的完整技能母集"
author: "Neo.K / EVEMISSLAB"
version: "v0.1"
status: "專用架構論文草案"
date: "2026-07-12"
language: "zh-TW"
keywords:
  - MUD
  - MSSP
  - AI Agent
  - Skill System
  - World Compiler
  - World IR
  - EML
  - AI GM
  - AI Player
  - Evennia
  - FluffOS
  - Rust Runtime
---

# MUD 世界工程 MSSP Skill System：可編譯世界、AI 協作與模組化 Agent 能力架構

## 摘要

本文在「MSSP-Scale Skill」通用方法論的基礎上，提出一套專門面向 MUD、文字多人世界、AI 世界生成與可編譯世界平台的完整技能母集架構。

本系統的目標不是建立一個只會產生房間描述、NPC 台詞或任務文字的單一 Skill，也不是建立一份巨型提示，讓 AI 同時扮演世界觀設計師、程式設計師、遊戲主持人、測試玩家與維運人員。本文主張，當 MUD 專案同時涉及小說文本匯入、世界觀解析、規則建模、地圖生成、任務狀態機、世界版本、存檔遷移、AI GM、AI 玩家、自動測試、多引擎輸出與正式部署時，它已不再是一項單純技能，而是一個完整的 Agent 能力系統。

因此，本文將 MUD 世界工程 Skill System 形式化為：

$$
\mathcal{M}_{\mathrm{MUD}}
=
(
F,
C,
S,
T,
D,
R,
X,
W
)
$$

其中：

- $F$：FMS，系統本體、範圍與導航；
- $C$：SCL，設定、權限、風險與世界修改契約；
- $S$：SMS，任何 MUD 世界工程閉環都不可缺少的核心技能；
- $T$：TMS，按需載入的引擎、世界來源、遊戲系統與 AI 角色能力；
- $D$：DMS，日誌、追蹤、測試報告與人類可見狀態；
- $R$：Router，根據任務選擇需要載入的技能子集；
- $X$：Runtime，實際工具、資料庫、程式執行與遊戲引擎；
- $W$：World IR／EML 世界中間表示。

本文進一步提出一個明確的世界工程閉環：

$$
\text{Source}
\rightarrow
\text{World Understanding}
\rightarrow
\text{World IR}
\rightarrow
\text{Validation}
\rightarrow
\text{Compilation}
\rightarrow
\text{Runtime}
\rightarrow
\text{Testing}
\rightarrow
\text{Patch}
\rightarrow
\text{Versioned Release}
$$

在此閉環中，AI 可以生成與提議，但不能無條件直接修改正式世界；玩家 Agent 可以探索與回報，但不能擁有後台真實狀態；程式 Agent 可以建立補丁與測試，但不能自行批准正式部署；GM Agent 可以提出事件與世界擴張，但不能越過世界公理與權限邊界。

本文的主要貢獻，是將「可編譯世界」從單一產品構想，轉換為一套可被實作、測試、版本化與持續擴張的 MSSP 規模 Skill System。

**關鍵詞：** MUD、MSSP、AI Agent、World Compiler、World IR、EML、AI GM、AI 玩家、世界版本、可編譯世界、Skill System

---

# 第一章　系統定位

## 1.1 這不是一個普通 MUD Skill

一般 MUD Skill 可能只需要完成以下工作：

- 建立房間；
- 建立 NPC；
- 產生物品；
- 撰寫任務；
- 生成地圖；
- 修改一個 MudLib；
- 為某一個引擎產生程式碼。

但本文要處理的系統同時包含：

- 小說全文匯入；
- 世界觀與規則解析；
- AI 從零生成世界；
- 世界公理與角色主觀信念區分；
- 地圖拓撲；
- 任務狀態機；
- 經濟與戰鬥規則；
- 世界版本與存檔版本；
- AI GM；
- AI 玩家；
- AI 測試；
- AI 程式修正；
- 多引擎輸出；
- 瀏覽器多人世界；
- 世界分叉與回滾；
- 未來動態 NPC；
- 未來 Agent 社會。

這些能力若全部放入單一 `SKILL.md`，將形成典型的提示單體。

因此，MUD 世界工程必須被視為一個技能母集系統。

---

## 1.2 正式定位

本文將本系統命名為：

> **MUD World Engineering MSSP Skill System**

其核心定位為：

> 將小說、世界觀、自然語言規則與既有 MUD 資料，轉換為可驗證、可編譯、可遊玩、可版本化與可持續擴張之文字世界的 Agent 技能母集。

MUD 是第一個可執行載體，但不是最終限制。

$$
W_{\mathrm{IR}}
\rightarrow
\begin{cases}
R_{\mathrm{Evennia}} \\
R_{\mathrm{FluffOS}} \\
R_{\mathrm{MudCore}} \\
R_{\mathrm{Rust}} \\
R_{\mathrm{Browser}} \\
R_{\mathrm{Simulation}}
\end{cases}
$$

---

## 1.3 核心目標

本系統應能完成以下主要任務：

1. 從小說或世界觀建立可遊玩世界；
2. 從零生成一個結構完整的 MUD；
3. 將 World IR 編譯到不同引擎；
4. 讓 AI 提議擴張與修改世界；
5. 讓 AI 玩家自動測試世界；
6. 建立可追蹤、可回滾的世界 Patch；
7. 管理世界版本、規則版本與存檔版本；
8. 將高風險程式與部署修改納入審查；
9. 為未來 AI GM、動態 NPC 與 Agent 社會保留接口。

---

## 1.4 非目標

第一版不以以下目標為必要條件：

- 完整取代現有 MUD 引擎；
- 直接讓 AI 在正式環境任意修改底層程式；
- 即時生成所有 NPC 思考；
- 實現完全自治的 Agent 社會；
- 將所有世界狀態都交給大型模型；
- 一開始支援所有 MUD 引擎；
- 一開始支援高風險多人商業部署。

---

# 第二章　總體形式化

## 2.1 系統結構

MUD 世界工程 Skill System 可表示為：

$$
\mathcal{M}_{\mathrm{MUD}}
=
(
F,
C,
S,
T,
D,
R,
X,
W
)
$$

其中：

- $F$：系統敘事、範圍、能力索引與架構圖；
- $C$：權限、修改等級、工具邊界與世界治理；
- $S$：世界工程核心技能；
- $T$：按需掛載的專用技能；
- $D$：診斷、追蹤、測試與報告；
- $R$：任務到技能集合的路由；
- $X$：檔案、資料庫、程式執行、AI API 與遊戲引擎；
- $W$：世界中間表示。

---

## 2.2 任務閉環

$$
Q
\xrightarrow{R}
(S_Q,T_Q,C_Q)
\xrightarrow{X}
O_Q
\xrightarrow{D}
V_Q
$$

其中：

- $Q$：使用者任務；
- $R$：路由；
- $S_Q$：必要 SMS；
- $T_Q$：必要 TMS；
- $C_Q$：適用的設定與權限契約；
- $X$：執行環境；
- $O_Q$：產出；
- $D$：診斷與驗證；
- $V_Q$：最終可交付結果。

---

## 2.3 世界閉環

$$
T_{\mathrm{source}}
\rightarrow
U_{\mathrm{world}}
\rightarrow
W_{\mathrm{IR}}
\rightarrow
V_{\mathrm{world}}
\rightarrow
C_{\mathrm{target}}
\rightarrow
S_{\mathrm{runtime}}
$$

其中：

- $T_{\mathrm{source}}$：來源文本或既有資料；
- $U_{\mathrm{world}}$：世界理解；
- $W_{\mathrm{IR}}$：世界中間表示；
- $V_{\mathrm{world}}$：世界驗證；
- $C_{\mathrm{target}}$：目標引擎編譯；
- $S_{\mathrm{runtime}}$：可遊玩狀態。

---

# 第三章　FMS：MUD 世界工程的系統憲法

## 3.1 FMS 的目的

FMS 應讓人類與 Agent 在不讀取全部子技能的情況下，迅速理解：

- 這套系統能做什麼；
- 它不做什麼；
- 核心世界模型是什麼；
- 哪些模組屬於核心；
- 哪些模組可插拔；
- 如何選擇引擎；
- 如何決定風險；
- 世界資料與底層執行如何分離；
- AI 修改何時需要審查。

---

## 3.2 FMS 目錄

```text
FMS/
├── 00_SYSTEM_NARRATIVE.md
├── 01_SCOPE_AND_NON_GOALS.md
├── 02_WORLD_ENGINEERING_MODEL.md
├── 03_ARCHITECTURE_MAP.md
├── 04_CAPABILITY_INDEX.yaml
├── 05_TERMINOLOGY.md
├── 06_ENGINE_COMPATIBILITY.md
├── 07_RISK_CLASSIFICATION.md
├── 08_VERSION_POLICY.md
├── 09_DECISION_LOG.md
└── 10_MAINTAINER_GUIDE.md
```

---

## 3.3 核心術語

FMS 應固定以下概念：

- World Source；
- World Understanding；
- World IR；
- EML World Layer；
- World Compiler；
- Runtime Adapter；
- World Patch；
- World Version；
- Rule Version；
- Save Version；
- AI GM；
- AI Player；
- Test Agent；
- Staging World；
- Production World；
- World Branch；
- World Snapshot；
- Event Log。

---

## 3.4 FMS 中的架構索引

```yaml
system:
  id: mud-world-engineering
  version: 0.1.0

core:
  - source-intake
  - world-understanding
  - world-ir
  - rule-validation
  - world-compiler
  - persistence
  - agent-governance
  - testing

adapters:
  - evennia
  - fluffos
  - mudcore
  - rust-runtime

agents:
  - world-builder
  - gm
  - player
  - programmer
  - reviewer
```

---

# 第四章　SCL：世界修改與 Agent 權限契約

## 4.1 為什麼 MUD Skill 特別需要 SCL

MUD 世界工程中的 Agent 可能同時接觸：

- 世界資料；
- 玩家資料；
- 任務；
- 程式碼；
- 存檔；
- 引擎；
- 正式部署；
- AI API；
- Git 儲存庫；
- 資料庫。

若沒有權限契約，AI 世界設計師與 AI 維運者之間將沒有明確邊界。

---

## 4.2 SCL 目錄

```text
SCL/
├── permissions.policy.yaml
├── world-mutation-levels.yaml
├── tool-access.yaml
├── data-boundaries.yaml
├── ai-provider-policy.yaml
├── runtime-limits.yaml
├── deployment-policy.yaml
├── save-migration-policy.yaml
├── publication-policy.yaml
└── approval-policy.yaml
```

---

## 4.3 世界修改分級

### L0：敘事層

- 房間描述；
- NPC 一般台詞；
- 書籍文本；
- 非關鍵背景。

### L1：內容層

- 新增房間；
- 新增普通 NPC；
- 新增非唯一物品；
- 新增支線任務；
- 新增低風險地圖區域。

### L2：規則參數層

- 傷害；
- 經驗值；
- 掉落率；
- 價格；
- 冷卻時間；
- 生成權重。

### L3：規則邏輯層

- 新戰鬥系統；
- 新任務判定；
- 新事件處理；
- 新技能邏輯；
- 新經濟循環。

### L4：核心與治理層

- 登入；
- 權限；
- 資料庫結構；
- 存檔格式；
- 網路協議；
- 正式部署；
- 刪除玩家資料；
- AI 工具權限。

---

## 4.4 Agent 權限矩陣

| 角色 | 可做 | 不可做 |
|---|---|---|
| World Builder | 產生世界草案、建立 Patch | 直接部署正式世界 |
| Rule Designer | 建立規則、檢查依賴 | 修改帳號與權限 |
| GM Agent | 提議事件與世界擴張 | 改寫硬公理 |
| Player Agent | 使用玩家指令、回報問題 | 查看後台真實狀態 |
| Test Agent | 重現錯誤、建立報告 | 自行批准補丁 |
| Programmer Agent | 建立程式碼補丁與測試 | 直接發布正式環境 |
| Reviewer Agent | 審查 Patch 與測試 | 自行提出並批准同一修改 |
| Release Controller | 發布已批准版本 | 生成未審查世界內容 |

---

## 4.5 權限形式化

設角色集合為 $A$，操作集合為 $O$。

$$
P : A \times O \rightarrow \{0,1\}
$$

若：

$$
P(a,o)=0
$$

則即使 Agent 知道如何執行 $o$，Runtime 也不應提供相應工具。

---

# 第五章　SMS：核心技能母集

## 5.1 SMS-01：Task and Intent Routing

### 目的

辨識使用者要求屬於：

- 新建世界；
- 匯入世界；
- 擴張世界；
- 修改規則；
- 產生引擎程式碼；
- 測試；
- 修復；
- 發布；
- 分析既有 MUD。

### 輸入

- 使用者請求；
- 現有世界狀態；
- 目標引擎；
- 風險；
- 可用工具。

### 輸出

- 任務類型；
- 必要 SMS；
- 必要 TMS；
- SCL 契約；
- 預期產物。

---

## 5.2 SMS-02：Source Intake

### 目的

處理所有世界來源：

- 小說；
- 世界觀設定；
- 角色表；
- 地圖；
- 規則；
- 既有 MudLib；
- JSON／YAML；
- EML；
- 使用者提示。

### 核心功能

- 檔案切分；
- 編碼偵測；
- 章節索引；
- 來源追蹤；
- 版權標記；
- 提示注入隔離；
- 來源可信度；
- 重複與衝突檢查。

### 輸出

標準化 Source Package。

---

## 5.3 SMS-03：World Understanding

### 目的

將來源資料轉換為世界理解模型。

### 抽取項目

- 世界公理；
- 角色；
- 地點；
- 勢力；
- 物種；
- 物品；
- 能力；
- 事件；
- 時間線；
- 地理關係；
- 角色關係；
- 規則候選；
- 缺失；
- 衝突；
- 不確定性。

### 重要區分

$$
\text{Character Belief}
\neq
\text{World Truth}
$$

角色相信某件事，不代表它是世界公理。

---

## 5.4 SMS-04：World IR／EML Core

### 目的

定義所有 TMS 與 Runtime 共用的世界中間表示。

### 核心實體

```text
world
axiom
entity
relation
region
room
exit
character
faction
item
ability
resource
rule
quest
event
timeline
economy
provenance
version
patch
```

### 最低結構

```yaml
world:
  id:
  version:
  title:
  genre:
  axioms: []
  regions: []
  entities: []
  rules: []
  quests: []
  events: []
  provenance: {}
```

### EML 的角色

EML 可以作為：

- 人類可讀世界描述；
- AI 可生成語義語言；
- World IR 前端；
- Patch 語言；
- 生命週期與持久性標記語言。

---

## 5.5 SMS-05：Rule and Consistency Validation

### 驗證類型

- Schema 驗證；
- 型別驗證；
- 世界公理；
- 規則衝突；
- 任務依賴；
- 地圖可達性；
- 物品可取得性；
- 經濟循環；
- 技能資源；
- 版本相容；
- 存檔相容；
- 引擎能力。

### 地圖可達率

$$
C_M
=
\frac{
|R_{\mathrm{reachable}}|
}{
|R_{\mathrm{all}}|
}
$$

### 任務依賴圖

$$
G_Q=(Q,E_Q)
$$

若存在無法滿足的前置路徑，該任務不得進入正式世界。

---

## 5.6 SMS-06：World Compiler

### 目的

將 World IR 編譯為目標 Runtime。

### 編譯階段

```text
World IR
→ Target Capability Check
→ Mapping
→ Code/Data Generation
→ Static Validation
→ Runtime Test
→ Package
```

### 目標輸出

- Evennia；
- FluffOS；
- MudCore；
- CoffeeMud；
- Rust Runtime；
- Browser Runtime；
- Simulation Runtime。

---

## 5.7 SMS-07：Persistence and Versioning

### 管理版本

```text
Engine Version
World Version
Rule Version
Schema Version
Save Version
AI Generation Version
Adapter Version
```

### 世界狀態

$$
S_t
=
\operatorname{Fold}
(
S_{t_0},
E_{t_0+1},
\ldots,
E_t
)
$$

### 必要能力

- Snapshot；
- Event Log；
- Save Migration；
- Rollback；
- Branch；
- Merge；
- World Diff；
- Patch History。

---

## 5.8 SMS-08：Agent Governance

### 目的

讓不同 AI 角色共享世界接口，但不共享全部權限。

### 管理項目

- 角色；
- 工具；
- 讀取範圍；
- 寫入範圍；
- 世界修改等級；
- 成本；
- 上下文；
- 模型；
- 審查流程；
- 失敗處理。

---

## 5.9 SMS-09：Testing and Simulation

### 測試範圍

- 單元測試；
- 引擎測試；
- 世界測試；
- AI 玩家；
- 任務覆蓋；
- 分支覆蓋；
- 地圖覆蓋；
- 經濟測試；
- 卡關測試；
- 惡意輸入；
- 存檔遷移；
- 回滾；
- 效能。

---

## 5.10 SMS-10：Result Assembly and Human Delivery

### 目的

將執行結果整理為使用者真正可用的產物。

### 產物可能包含

- MD 設計文件；
- World IR；
- EML；
- JSON；
- Python；
- LPC；
- Rust；
- 測試報告；
- 世界預覽；
- 可下載壓縮包；
- Git Patch；
- 部署說明。

---

# 第六章　TMS：專用技能子集

## 6.1 引擎適配 TMS

```text
TMS/adapters/evennia
TMS/adapters/fluffos
TMS/adapters/mudcore
TMS/adapters/coffeemud
TMS/adapters/rust-runtime
TMS/adapters/browser-runtime
```

每個 Adapter 必須聲明：

- 支援的 World IR 能力；
- 不支援的能力；
- 編譯策略；
- 版本；
- 測試；
- 存檔相容；
- 部署方式。

---

## 6.2 世界來源 TMS

```text
TMS/sources/novel-import
TMS/sources/world-bible
TMS/sources/legacy-mudlib
TMS/sources/json-world
TMS/sources/eml-world
TMS/sources/ai-generated-world
```

---

## 6.3 AI 角色 TMS

```text
TMS/agents/world-builder
TMS/agents/gm
TMS/agents/player
TMS/agents/programmer
TMS/agents/reviewer
TMS/agents/release-controller
```

---

## 6.4 遊戲系統 TMS

```text
TMS/systems/combat
TMS/systems/quest
TMS/systems/economy
TMS/systems/faction
TMS/systems/crafting
TMS/systems/magic
TMS/systems/survival
TMS/systems/reputation
TMS/systems/dialogue
TMS/systems/dynamic-npc
```

---

## 6.5 發布模式 TMS

```text
TMS/publishing/single-player
TMS/publishing/multiplayer
TMS/publishing/private-world
TMS/publishing/public-world
TMS/publishing/web-client
TMS/publishing/mod-export
```

---

## 6.6 分析與遷移 TMS

```text
TMS/analysis/legacy-code
TMS/analysis/world-dependency
TMS/analysis/save-growth
TMS/analysis/performance
TMS/migration/world-schema
TMS/migration/save-version
```

---

# 第七章　DMS：MUD 世界工程的觀測系統

## 7.1 為什麼需要 DMS

AI 生成世界後，只說「已完成」毫無意義。

使用者需要知道：

- 世界建立了多少區域；
- 有多少房間；
- 有多少任務；
- 是否存在不可達區域；
- 是否有規則衝突；
- 哪些內容是 AI 推導；
- 哪些內容來自原作；
- 目前版本；
- 是否已測試；
- 是否部署。

---

## 7.2 DMS 目錄

```text
DMS/
├── task-trace/
├── world-reports/
├── validation-reports/
├── agent-reports/
├── test-reports/
├── cost-reports/
├── deployment-reports/
├── audit-log/
└── human-visible-state/
```

---

## 7.3 世界報告

```yaml
world_report:
  world_version: 0.1.0
  regions: 5
  rooms: 286
  characters: 43
  factions: 7
  quests: 34
  rules: 87

validation:
  schema_errors: 0
  rule_conflicts: 3
  unreachable_rooms: 2
  impossible_quests: 1

testing:
  room_coverage: 0.82
  quest_coverage: 0.74
  branch_coverage: 0.61
```

---

# 第八章　Router：任務到技能集合的映射

## 8.1 路由原則

不應每次載入全部 MUD Skill。

例如：

> 將一本小說轉成 Evennia 單人世界。

只需載入：

```text
FMS-Minimal
SCL-Read-Create
SMS-Intent-Routing
SMS-Source-Intake
SMS-World-Understanding
SMS-World-IR
SMS-Validation
SMS-World-Compiler
SMS-Persistence
SMS-Testing
TMS-Novel-Import
TMS-Evennia
TMS-Single-Player
```

不需要載入：

- FluffOS；
- CoffeeMud；
- AI GM；
- AI Programmer；
- 多人世界；
- 動態 NPC；
- 公開發布。

---

## 8.2 路由形式

$$
R(q)
=
F_{\min}
\cup
C_q
\cup
S_q
\cup
T_q
$$

---

## 8.3 路由示例

### 任務 A：建立小說世界

```yaml
task_type: world_creation
source: novel
target: evennia
mode: single_player
risk: 1
```

### 任務 B：新增戰鬥規則

```yaml
task_type: rule_change
system: combat
target: existing_world
risk: 3
requires_approval: true
```

### 任務 C：AI 玩家測試

```yaml
task_type: automated_playtest
agent_profile: exploit_player
access: player_only
risk: 1
```

---

# 第九章　World IR 與 EML 的核心位置

## 9.1 World IR 是跨引擎共同契約

若所有功能直接依賴 Evennia 或 FluffOS，系統便無法成為真正世界平台。

因此：

$$
\mathrm{TMS}_{\mathrm{source}}
\rightarrow
W_{\mathrm{IR}}
\rightarrow
\mathrm{TMS}_{\mathrm{adapter}}
$$

---

## 9.2 EML 作為前端世界語言

$$
T_{\mathrm{natural}}
\rightarrow
\mathrm{EML}_{\mathrm{world}}
\rightarrow
W_{\mathrm{IR}}
\rightarrow
R_{\mathrm{target}}
$$

EML 可以描述：

- 世界公理；
- 實體；
- 關係；
- 規則；
- 任務；
- 生命週期；
- 持久性；
- Patch；
- 測試要求。

---

## 9.3 示例

```eml
world black_tide_city {
    version: 0.1.0

    axiom magic_memory_cost {
        enforcement: hard
    }

    region gray_crown {
        room south_gate
        room market
        connect south_gate -> market by north
    }

    rule cast_memory_spell {
        when spell.school == memory
        apply actor.memory -= 3
    }
}
```

---

# 第十章　AI 世界建構流程

## 10.1 世界建立

```text
使用者輸入
→ 來源分析
→ 世界理解報告
→ 缺失與衝突
→ World IR 草案
→ 驗證
→ 編譯
→ AI 玩家測試
→ 世界報告
→ 建立實例
```

---

## 10.2 世界擴張

```text
使用者提出修改
→ AI 分析影響
→ 產生 Patch
→ 公理檢查
→ 依賴檢查
→ 模擬
→ Staging
→ 回歸測試
→ 發布
```

---

## 10.3 Patch

```yaml
patch:
  id: northern_expansion_001
  base_world_version: 0.4.2
  target_world_version: 0.5.0
  risk_level: 1
  reason: 新增北方地區

operations:
  - add_region
  - add_rooms
  - add_quests

validation:
  map_reachability: required
  quest_dependency: required
  save_compatibility: required
```

---

# 第十一章　AI 玩家與測試閉環

## 11.1 玩家 Agent 類型

- 新手；
- 探索者；
- 劇情玩家；
- 速通玩家；
- 惡意玩家；
- 經濟套利者；
- 指令亂輸入者；
- 長期掛機者；
- 團隊玩家；
- 世界破壞者。

---

## 11.2 測試指標

$$
C_R =
\frac{
|R_{\mathrm{visited}}|
}{
|R_{\mathrm{all}}|
}
$$

$$
C_Q =
\frac{
|Q_{\mathrm{completed}}|
}{
|Q_{\mathrm{all}}|
}
$$

$$
C_B =
\frac{
|B_{\mathrm{executed}}|
}{
|B_{\mathrm{defined}}|
}
$$

另需監測：

- 死亡原因；
- 軟鎖；
- 永久卡關；
- 無限資源；
- 無限經驗；
- 任務斷鏈；
- 無出口房間；
- API 成本；
- 回應延遲；
- 伺服器錯誤。

---

## 11.3 自動修正閉環

```text
AI 玩家發現問題
→ Test Agent 重現
→ Rule Agent 判斷
→ Programmer Agent 提交補丁
→ Reviewer Agent 審查
→ Staging 測試
→ Release Controller 發布
```

同一 Agent 不得同時完成全部步驟。

---

# 第十二章　引擎適配策略

## 12.1 Evennia

適合：

- Python 開發；
- 快速原型；
- AI API；
- Web Client；
- 單人與多人；
- 測試工具；
- World IR Adapter。

第一版優先適配。

---

## 12.2 FluffOS／MudCore

適合：

- 傳統中文 MUD；
- LPC 生態；
- 舊 MudLib 遷移；
- 中文社群資產。

需要處理：

- LPC 生成；
- MudLib 約定；
- 編碼；
- 舊資料格式；
- 安全沙盒。

---

## 12.3 Rust Runtime

適合：

- 未來自研世界核心；
- 高效區塊串流；
- 長期世界；
- 多 Agent 模擬；
- 受控並行；
- EML 原生 Runtime。

不建議作為第一個 MVP。

---

# 第十三章　完整目錄建議

```text
mud-world-engineering-skill/
├── SKILL.md
│
├── FMS/
│   ├── 00_SYSTEM_NARRATIVE.md
│   ├── 01_SCOPE_AND_NON_GOALS.md
│   ├── 02_WORLD_ENGINEERING_MODEL.md
│   ├── 03_ARCHITECTURE_MAP.md
│   ├── 04_CAPABILITY_INDEX.yaml
│   ├── 05_TERMINOLOGY.md
│   ├── 06_ENGINE_COMPATIBILITY.md
│   ├── 07_RISK_CLASSIFICATION.md
│   ├── 08_VERSION_POLICY.md
│   └── 09_DECISION_LOG.md
│
├── SCL/
│   ├── permissions.policy.yaml
│   ├── world-mutation-levels.yaml
│   ├── tool-access.yaml
│   ├── data-boundaries.yaml
│   ├── runtime-limits.yaml
│   ├── deployment-policy.yaml
│   └── approval-policy.yaml
│
├── SMS/
│   ├── intent-routing/
│   ├── source-intake/
│   ├── world-understanding/
│   ├── world-ir/
│   ├── rule-validation/
│   ├── world-compiler/
│   ├── persistence/
│   ├── agent-governance/
│   ├── testing/
│   └── result-assembly/
│
├── TMS/
│   ├── adapters/
│   │   ├── evennia/
│   │   ├── fluffos/
│   │   ├── mudcore/
│   │   └── rust-runtime/
│   ├── sources/
│   │   ├── novel/
│   │   ├── world-bible/
│   │   ├── legacy-mudlib/
│   │   └── eml/
│   ├── agents/
│   │   ├── world-builder/
│   │   ├── gm/
│   │   ├── player/
│   │   ├── programmer/
│   │   └── reviewer/
│   ├── systems/
│   │   ├── combat/
│   │   ├── quest/
│   │   ├── economy/
│   │   ├── faction/
│   │   ├── crafting/
│   │   └── dynamic-npc/
│   └── publishing/
│       ├── single-player/
│       ├── multiplayer/
│       └── browser-world/
│
├── DMS/
│   ├── world-reports/
│   ├── validation-reports/
│   ├── test-reports/
│   ├── cost-reports/
│   ├── audit-log/
│   └── human-visible-state/
│
├── schemas/
├── templates/
├── examples/
├── tests/
├── migrations/
└── scripts/
```

---

# 第十四章　最小可行 Skill System

## 14.1 第一版必需

```text
FMS
SCL
SMS-Intent-Routing
SMS-Source-Intake
SMS-World-Understanding
SMS-World-IR
SMS-Validation
SMS-World-Compiler
SMS-Persistence
SMS-Testing
TMS-Novel-Import
TMS-Evennia
TMS-Single-Player
```

---

## 14.2 第一個閉環

$$
\text{小說}
\rightarrow
\text{世界理解}
\rightarrow
\text{World IR／EML}
\rightarrow
\text{驗證}
\rightarrow
\text{Evennia}
\rightarrow
\text{AI 玩家測試}
\rightarrow
\text{可遊玩單人世界}
$$

---

## 14.3 第一版暫不包含

- 多人正式世界；
- 動態 NPC；
- AI 自動改核心程式；
- FluffOS 正式適配；
- Rust Runtime；
- 公開世界市集；
- Agent 社會。

---

# 第十五章　開發階段

## Phase 0：能力盤點與規格

- 固定 FMS；
- 固定 World IR 最小結構；
- 固定世界修改等級；
- 固定角色權限；
- 固定第一個目標引擎。

## Phase 1：來源到 World IR

- 小說匯入；
- 世界理解；
- 公理；
- 角色；
- 地點；
- 地圖；
- 任務；
- 規則。

## Phase 2：World IR 到 Evennia

- Adapter；
- 房間；
- 出口；
- NPC；
- 物品；
- 任務；
- 存檔。

## Phase 3：驗證與 AI 玩家

- 可達性；
- 任務依賴；
- AI 探索；
- 卡關；
- 世界報告。

## Phase 4：Patch 與版本

- 世界修改；
- Diff；
- Staging；
- Rollback；
- Save Migration。

## Phase 5：多引擎

- FluffOS；
- MudCore；
- Browser Runtime。

## Phase 6：AI GM 與動態世界

- 動態事件；
- 受控世界擴張；
- AI GM；
- 長期世界演化。

## Phase 7：Rust Runtime 與 Agent 社會

- 高效世界核心；
- 多尺度模擬；
- 大量 AI 玩家；
- 動態 NPC；
- Agent 社會。

---

# 第十六章　測試策略

## 16.1 Skill 測試

- Router 測試；
- 契約測試；
- TMS 孤島測試；
- 權限測試；
- 工具失敗測試；
- 版本相容測試。

## 16.2 世界測試

- 地圖；
- 任務；
- 經濟；
- 戰鬥；
- NPC；
- 存檔；
- 版本遷移；
- 回滾。

## 16.3 安全測試

- 小說提示注入；
- AI 越權；
- 程式碼沙盒；
- 正式資料保護；
- 玩家資料隔離；
- 第三方 Mod。

---

# 第十七章　主要反模式

## 17.1 巨型 MUD Skill

所有引擎、所有 AI 角色與所有遊戲系統都塞進同一份文件。

## 17.2 引擎綁死

World IR 直接等於 Evennia 模型或 FluffOS MudLib。

## 17.3 AI 直接改正式程式

沒有 Patch、測試、審查與回滾。

## 17.4 AI 玩家擁有後台視角

導致測試失真。

## 17.5 世界與存檔版本混合

新世界規則直接破壞舊存檔。

## 17.6 TMS 網狀依賴

AI GM 直接依賴 Evennia，戰鬥系統直接依賴某一資料庫。

## 17.7 沒有世界報告

使用者無法知道生成世界是否可用。

---

# 第十八章　開源與商業邊界

## 18.1 建議開源

- World IR；
- EML 世界子集；
- Schema；
- 基礎驗證器；
- 基礎 World Compiler；
- Evennia Adapter；
- 測試框架；
- Patch 格式；
- 範例世界。

## 18.2 可保留

- 高階 Agent 編排；
- 世界品質評分；
- 商業模型路由；
- 大規模 AI 玩家叢集；
- 自動程式修正閉環；
- 內部風險控制；
- 世界自演化核心。

---

# 第十九章　理論意義

## 19.1 MUD 是世界工程的最小可行載體

MUD 不需要大量美術，卻完整保留：

- 空間；
- 角色；
- 規則；
- 任務；
- 經濟；
- 社會；
- 歷史；
- 多人互動。

因此它是 AI 世界工程最適合的第一個實戰環境。

---

## 19.2 Skill System 是世界編譯器的認知層

World Compiler 負責把世界資料轉換成可執行內容。

MSSP Skill System 負責決定：

- 誰建立世界；
- 如何理解來源；
- 哪些能力應載入；
- 如何驗證；
- 誰能修改；
- 如何測試；
- 如何發布。

因此：

$$
\mathrm{WorldCompiler}
\subset
\mathrm{MSSP\ SkillSystem}
$$

---

## 19.3 AI 不只是內容生成器

在此系統中，AI 可以依序成為：

- 世界理解者；
- 世界設計者；
- 規則設計者；
- 程式設計者；
- 玩家；
- 測試者；
- 審查者；
- GM；
- 維運者。

但每一種身份都必須有不同上下文與權限。

---

# 第二十章　結論

本文提出 MUD World Engineering MSSP Skill System，將 MUD 世界生成、世界編譯、AI 協作、測試、版本與治理整合為一套完整的技能母集架構。

其核心結構為：

```text
FMS：定義 MUD 世界工程系統是什麼
SCL：定義誰可以如何修改世界與程式
SMS：保存世界工程不可缺少的核心能力
TMS：保存引擎、來源、AI 角色與遊戲系統能力
DMS：呈現世界、測試與執行狀態
Router：只載入當前任務真正需要的能力
Runtime：連接 AI、檔案、資料庫、程式與遊戲引擎
World IR／EML：作為跨引擎共同世界契約
```

第一個可行閉環為：

$$
\text{小說}
\rightarrow
\text{World IR／EML}
\rightarrow
\text{Evennia}
\rightarrow
\text{AI 玩家測試}
\rightarrow
\text{可遊玩世界}
$$

當這個閉環成立後，系統才能合理擴張到：

- 多人世界；
- AI GM；
- 動態 NPC；
- FluffOS；
- Rust Runtime；
- 瀏覽器共同世界；
- AI 玩家社會；
- 世界長期演化。

本系統的真正目標，不是建立一個會寫 MUD 的 AI，而是建立：

> 一套能讓人類與 AI 共同理解、生成、編譯、測試、修改、治理與持續演化數位世界的技能母集。

---

# 附錄 A　母 Skill Manifest

```yaml
system:
  id: mud-world-engineering
  version: 0.1.0
  architecture: MSSP

fms:
  narrative: FMS/00_SYSTEM_NARRATIVE.md
  capability_index: FMS/04_CAPABILITY_INDEX.yaml

scl:
  permissions: SCL/permissions.policy.yaml
  mutation_levels: SCL/world-mutation-levels.yaml
  deployment: SCL/deployment-policy.yaml

sms:
  - intent-routing
  - source-intake
  - world-understanding
  - world-ir
  - rule-validation
  - world-compiler
  - persistence
  - agent-governance
  - testing
  - result-assembly

tms:
  adapters:
    - evennia
    - fluffos
    - mudcore
    - rust-runtime
  sources:
    - novel
    - world-bible
    - legacy-mudlib
    - eml
  agents:
    - world-builder
    - gm
    - player
    - programmer
    - reviewer

dms:
  - world-reports
  - validation-reports
  - test-reports
  - audit-log
```

---

# 附錄 B　MUD TMS 契約模板

```yaml
id:
name:
version:
layer: TMS
category:
  - adapter
  - source
  - agent
  - system
  - publishing

purpose:

activate_when:

inputs:

outputs:

world_ir_capabilities:

requires:
  sms: []
  tools: []
  data: []

permissions:
  may: []
  may_not: []

risk_level:

validation:

tests:

compatibility:

failure_modes:

maintainer:
```

---

# 附錄 C　第一版實作清單

- [ ] 建立母 `SKILL.md`
- [ ] 建立 FMS 系統敘事
- [ ] 建立能力索引
- [ ] 建立 SCL 權限契約
- [ ] 建立世界修改等級
- [ ] 建立 World IR Schema
- [ ] 建立 EML 世界最小子集
- [ ] 建立小說匯入 TMS
- [ ] 建立 Evennia Adapter
- [ ] 建立地圖可達性測試
- [ ] 建立任務依賴測試
- [ ] 建立 AI 新手玩家
- [ ] 建立 AI 探索玩家
- [ ] 建立世界報告
- [ ] 建立 Patch 格式
- [ ] 建立 Snapshot 與 Event Log
- [ ] 建立第一個可下載範例世界
