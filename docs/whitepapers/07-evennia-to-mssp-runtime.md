---
title: "從 Evennia 參考實作到 MSSP 模組化世界執行引擎：CompilableWorld Runtime 的重構原則"
subtitle: "以 MUD 為第一介面、以世界狀態機為核心、以機制與 UI 解耦為基礎的自研遊戲引擎架構"
author: "Neo.K / EVEMISSLAB"
version: "v0.1"
status: "核心架構重構文件"
date: "2026-07-13"
language: "zh-TW"
keywords:
  - MSSP
  - CompilableWorld
  - MUD
  - World Runtime
  - Game Engine
  - Modular Architecture
  - State Machine
  - UI Decoupling
  - Event Bus
  - World Kernel
  - Evennia
---

# 從 Evennia 參考實作到 MSSP 模組化世界執行引擎：CompilableWorld Runtime 的重構原則

## 摘要

本文提出 CompilableWorld 遊戲專案從既有 MUD 框架改造路線，正式轉向自研 MSSP 模組化世界執行引擎的架構決策。

早期採用 Evennia 作為驗證工具是合理的。它提供 Python、Django、帳號、角色、網頁客戶端、命令系統、持久化與多人連線等現成功能，適合快速建立傳統 MUD 原型。然而，當專案目標逐步擴張為：

- 大型小說與世界觀改編；
- JSON、CSV、EML 與 Manifest 來源層；
- CompilableWorld 世界編譯；
- State IR、Action IR、Event IR；
- 超大型階層式有限狀態世界；
- AI 自然語言行為編譯；
- MSSP 機制模組；
- 多種 UI；
- Agent 治理；
- 世界版本、事件溯源與重播；
- 未來多遊戲型態與多執行環境；

Evennia 的原始抽象便不再足以作為核心。

問題不在授權，也不只是程式碼品質，而是架構本體不同。Evennia 主要以 MU* 遊戲框架為中心；本專案需要的是一個以世界狀態、行為、事件、機制模組與跨介面輸出為核心的通用世界 Runtime。

因此，本文主張：

> Evennia 應從核心引擎降為參考實作、原型工具與相容適配目標；真正的遊戲核心應重新建立為 MSSP Modular World Runtime。

其總體架構為：

$$
\mathrm{CompilableWorld\ Runtime}
=
K+M+P+V+A+O
$$

其中：

- $K$：World Kernel，世界執行核心；
- $M$：MSSP Mechanism Modules，遊戲機制模組；
- $P$：Protocol and Gateway，指令、網路與外部介面；
- $V$：View and UI Layer，呈現與互動介面；
- $A$：AI and Agent Layer，自然語言、世界生成與 Agent 協作；
- $O$：Observability and Operations，監控、測試、事件歷史與維運。

本文進一步定義 World Kernel 的最小責任、MSSP 模組契約、UI 與機制解耦方式、狀態與事件提交模型、Evennia 相容層，以及分階段重寫策略。

---

# 第一章　架構決策背景

## 1.1 Evennia 在早期階段的價值

Evennia 提供了以下能力：

- Python 開發環境；
- 多人 MUD 伺服器；
- 命令解析；
- 帳號與角色；
- Django 網站；
- Web Client；
- 資料庫；
- 物件與腳本系統；
- Telnet 與 WebSocket；
- 管理後台；
- 快速原型。

對一般 MUD 而言，這些能力已經相當完整。

對本專案而言，它也曾適合用來驗證：

- 世界是否能載入；
- 角色是否能互動；
- 房間與出口是否能建立；
- 網頁 UI 是否可行；
- AI 生成資料能否轉為遊戲內容。

## 1.2 問題不是授權

Evennia 採寬鬆授權，商業使用本身不是主要障礙。

真正問題是：

1. 核心抽象仍以傳統 MU* 為中心；
2. 世界資料、遊戲邏輯與框架生命週期高度相關；
3. 自訂大型狀態機與事件模型需要大量繞行；
4. CompilableWorld 會被迫適配 Evennia，而不是由 Runtime 適配 World IR；
5. UI 與 Web 架構雖可擴充，但不天然等同於多前端 View Model；
6. 機制模組無法自然對應 MSSP；
7. AI Agent 權限與 Patch 治理不是核心設計；
8. 多 Runtime、多遊戲型態與跨引擎輸出不是其主要目標。

## 1.3 繼續大改的代價

若繼續以 Evennia 為核心，可能形成：

```text
理解 Evennia 內部模型
→ 繞過框架生命週期
→ 修改物件與狀態管理
→ 重建事件系統
→ 增加 Action IR
→ 增加 CompilableWorld Loader
→ 拆分 UI
→ 重建模組契約
→ 重建 Agent 權限
→ 重建版本與事件溯源
```

當需要重寫的內容超過被保留的核心價值時，Fork 便不再是節省成本，而會變成長期限制。

---

# 第二章　新的正式定位

## 2.1 MUD 不再等於完整遊戲引擎

本專案中的 MUD 應重新定義為：

> 一種以文字指令、自然語言與事件輸出操作世界狀態的底層互動模式。

因此：

$$
\mathrm{MUD}
\subset
\mathrm{World\ Runtime}
$$

MUD 是第一個介面，不是整個引擎。

## 2.2 MUD Core 的責任

MUD Core 可包含：

- 文字命令；
- 自然語言行為輸入；
- 實體引用；
- 狀態查詢；
- 事件回傳；
- 多人 Session；
- 基礎文字敘事輸出。

但不應綁死：

- 戰鬥面板；
- 地圖 UI；
- 世界編輯器；
- AI 控制台；
- 管理員後台；
- 手機版介面；
- 桌面遊戲呈現；
- 特定任務畫面。

## 2.3 新引擎名稱

建議正式定位為：

> **MSSP Modular World Runtime**

亦可稱：

> **CompilableWorld Runtime Engine**

其目標不是只建立一款 MUD，而是建立一個可支援：

- 純文字 MUD；
- 互動小說；
- AI RPG；
- 多人文字世界；
- 世界模擬；
- Agent 社會；
- Web RPG；
- 桌面 RPG；
- 世界編輯與推演工具；

的通用世界執行核心。

---

# 第三章　總體架構

## 3.1 完整資料與執行流程

```text
Novel / World Source
        ↓
World Adaptation Skill
        ↓
JSON / CSV / EML / Manifest
        ↓
CompilableWorld Compiler
        ↓
World IR / State IR / Action IR / Event IR
        ↓
MSSP Modular World Runtime
        ↓
Mechanism Modules
        ↓
State Delta / Event / View Model
        ↓
UI Adapters
```

## 3.2 系統形式化

$$
\mathcal{R}_{W}
=
(K,M,G,V,A,D)
$$

其中：

- $K$：Kernel；
- $M$：Mechanism Modules；
- $G$：Gateway and Protocol；
- $V$：View Layer；
- $A$：AI and Agent Layer；
- $D$：Diagnostics and Operations。

---

# 第四章　World Kernel

## 4.1 Kernel 應保持最小化

World Kernel 不負責「遊戲好不好玩」，只負責世界是否能正確執行。

```text
World Kernel
├── Entity Registry
├── State Store
├── Action Runtime
├── Transition Engine
├── Event Bus
├── Scheduler
├── Permission Engine
├── Module Runtime
├── Persistence
├── Snapshot / Replay
├── Transaction / Delta Commit
└── Protocol Gateway
```

## 4.2 Entity Registry

負責：

- Entity ID；
- Entity Type；
- Component；
- 所屬世界；
- 所屬區域；
- Module Extension；
- 引用解析；
- Entity Lifecycle。

Kernel 不需要知道「狼人」的完整遊戲意義，只需要知道：

```yaml
entity:
  id: npc_wolf_001
  type: character
  components:
    - health
    - location
    - combatant
    - perception
```

## 4.3 State Store

State Store 保存當前世界狀態。

```yaml
state:
  owner: npc_wolf_001
  namespace: combat
  key: health
  value: 74
  version: 18
```

所有狀態修改必須經過統一提交，而不是由模組任意寫入資料庫。

## 4.4 Action Runtime

Action Runtime 處理：

```text
Proposed
→ Parsed
→ Validated
→ Scheduled
→ Executing
→ Completed / Failed / Interrupted
```

Action 不只是瞬間命令，也可以是：

- 多步驟；
- 有時長；
- 可中斷；
- 可取消；
- 可等待；
- 可並行；
- 可重試。

## 4.5 Transition Engine

轉移規則：

$$
r:(S,A,C)\rightarrow(\Delta S,E)
$$

Kernel 接收：

- 原始狀態；
- 行為；
- 上下文；
- 模組規則；

產生：

- State Delta；
- Event；
- 驗證結果。

## 4.6 Event Bus

模組之間不直接呼叫彼此內部邏輯。

```text
Combat Module
→ combat.damage_applied
→ Health Module
→ Quest Module
→ UI Projection
→ Audit Log
```

事件應有：

- Type；
- Source；
- Target；
- Causation ID；
- Correlation ID；
- Timestamp；
- Payload；
- Visibility；
- Authority；
- Version。

## 4.7 Scheduler

管理：

- Tick；
- Turn；
- Real-time；
- Delayed Event；
- Recurring Event；
- Action Duration；
- Cooldown；
- World Time；
- Pause；
- Offline Simulation。

## 4.8 Permission Engine

決定：

- 哪個玩家能做什麼；
- 哪個 Agent 能讀什麼；
- 哪個模組能改什麼；
- 哪些狀態是私人；
- 哪些操作需要批准；
- 哪些世界 Patch 可以自動發布。

## 4.9 Persistence

Kernel 應支援：

- Snapshot；
- Event Log；
- Save Version；
- Migration；
- Rollback；
- Branch；
- World Instance；
- Player State；
- Module State。

---

# 第五章　MSSP 機制模組

## 5.1 機制不屬於 Kernel

以下不應寫死在核心：

- Combat；
- Quest；
- Economy；
- Crafting；
- Magic；
- Law；
- Reputation；
- Dialogue；
- Survival；
- Faction；
- Weather；
- AI NPC；
- AI GM。

它們應作為 MSSP TMS 模組。

## 5.2 建議目錄

```text
modules/
├── SMS/
│   ├── entity/
│   ├── state/
│   ├── action/
│   ├── event/
│   ├── persistence/
│   ├── permission/
│   └── scheduling/
│
└── TMS/
    ├── combat/
    ├── quest/
    ├── economy/
    ├── faction/
    ├── law/
    ├── crafting/
    ├── magic/
    ├── dialogue/
    ├── survival/
    ├── reputation/
    ├── ai-gm/
    ├── ai-npc/
    └── world-generation/
```

## 5.3 Module Contract

每個模組必須聲明：

```yaml
module:
  id: combat.core
  version: 0.1.0
  layer: TMS

requires:
  kernel:
    - entity
    - state
    - action
    - event

provides:
  states:
    - combat.health
    - combat.stamina

  actions:
    - combat.attack
    - combat.defend

  events:
    - combat.damage_applied
    - combat.actor_defeated

permissions:
  read:
    - entity.location
    - combat.*
  write:
    - combat.*

ui_projection:
  - combat.status
  - combat.timeline
```

## 5.4 模組不得直接修改外部狀態

錯誤：

```python
player.health -= 12
```

正確：

```yaml
state_delta:
  owner: player_001
  namespace: combat
  key: health
  operation: subtract
  value: 12
  source: combat.damage
```

由 Kernel：

1. 驗證權限；
2. 驗證版本；
3. 解決衝突；
4. 提交 Delta；
5. 產生事件；
6. 寫入歷史。

## 5.5 Island Test

每個 TMS 應能在以下環境獨立測試：

```text
Minimal Kernel
+ Mock Entity
+ Mock State
+ Mock Event Bus
+ Target Module
```

若 Combat 模組必須啟動 Quest、Economy 與完整 UI 才能測試，表示存在隱藏耦合。

---

# 第六章　UI 與機制分離

## 6.1 同一機制，多種呈現

同一個事件：

```yaml
event:
  type: combat.damage_applied
  source: npc_wolf_001
  target: player_001
  amount: 12
  damage_type: bleeding
  body_part: left_arm
```

可以被不同 UI 呈現。

## 6.2 文字 MUD UI

```text
狼爪撕裂了你的左臂，你受到 12 點流血傷害。
```

## 6.3 Web UI

- 血條下降；
- 左臂受傷；
- 流血圖示；
- 傷害數字；
- 戰鬥時間線。

## 6.4 管理 UI

- Event ID；
- Rule Version；
- State Before；
- State After；
- Processing Time；
- Module Source；
- Correlation Trace。

## 6.5 View Model

機制事件不應直接等於 UI。

應建立：

```text
World Event
→ Projection
→ View Model
→ UI Adapter
```

例如：

```yaml
view_model:
  type: combat_status
  actor: player_001
  health:
    current: 74
    max: 100
  conditions:
    - bleeding
  recent_changes:
    - amount: -12
      source: wolf_claw
```

## 6.6 UI Adapter

```text
ui/
├── terminal/
├── web/
├── desktop/
├── mobile/
├── admin/
├── editor/
└── ai-interface/
```

每個 UI 只處理：

- Input Mapping；
- View Rendering；
- Session；
- Accessibility；
- Local Cache；
- Client Interaction。

UI 不執行核心規則。

---

# 第七章　Protocol Gateway

## 7.1 支援多種輸入

Gateway 可接受：

- 傳統 MUD 指令；
- 自然語言；
- Web Button；
- REST；
- WebSocket；
- Agent Tool Call；
- Script；
- Replay；
- Test Harness。

所有輸入最終轉為 Action IR。

## 7.2 統一行為入口

$$
I_i\xrightarrow{g_i}A_{\mathrm{IR}}
$$

其中 $I_i$ 可為：

- 文字；
- UI 點擊；
- API；
- AI Agent；
- 自動測試。

Runtime 只接收 Action IR，不關心輸入來自哪個介面。

---

# 第八章　CompilableWorld 與 Runtime

## 8.1 CompilableWorld 負責定義

包括：

- 世界資料；
- Entity Prototype；
- State Definition；
- Action Definition；
- Transition Rule；
- Event Contract；
- Permission；
- Module Requirement；
- UI Projection Requirement。

## 8.2 Runtime 負責執行

Runtime 不重新理解整個世界，只載入已編譯內容。

```text
World Seed Package
→ Compiler
→ Validated World Package
→ Runtime Loader
→ World Instance
```

## 8.3 Runtime Package

```text
compiled-world/
├── manifest.json
├── entities.bin / json
├── states.json
├── actions.json
├── transitions.json
├── events.json
├── permissions.json
├── modules.lock
├── projections.json
├── migration/
└── checksums.json
```

---

# 第九章　AI 與 Agent Layer

## 9.1 AI 不屬於 Kernel

AI 可以：

- 解析自然語言；
- 建立 Action IR；
- 生成局部敘事；
- 提議世界 Patch；
- 測試世界；
- 分析錯誤；
- 控制 NPC；
- 擔任 GM。

但 Kernel 必須在無 AI 的情況下仍可執行世界基本規則。

## 9.2 Agent 分權

```text
World Builder Agent
Rule Agent
GM Agent
NPC Agent
Player Agent
Test Agent
Programmer Agent
Reviewer Agent
Release Agent
```

每個 Agent 透過不同工具與權限接觸 Runtime。

## 9.3 AI Runtime Adapter

```text
Natural Language
→ Intent Parser
→ Action Candidate
→ Validator
→ Action IR
→ Kernel
```

AI 不直接提交資料庫修改。

---

# 第十章　DMS：觀測與維運

## 10.1 必要觀測

- Entity Count；
- Action Throughput；
- Event Throughput；
- Module Errors；
- State Conflict；
- Scheduler Lag；
- Persistence Latency；
- AI Cost；
- Player Session；
- World Version；
- Replay Integrity。

## 10.2 Human-Visible State

開發者應能看到：

```text
目前載入哪些模組
每個模組版本
世界版本
狀態數量
事件佇列
失敗 Action
衝突 Delta
最近 Patch
資料庫健康
```

---

# 第十一章　Evennia 的新定位

## 11.1 Reference Implementation

Evennia 可供參考：

- MUD 命令；
- 帳號；
- Session；
- Telnet；
- WebSocket；
- Web Client；
- Object 模型；
- Persistent Script；
- 管理工具。

## 11.2 Prototype Target

部分 World Seed 可先輸出到 Evennia，用於：

- 快速試玩；
- 驗證地圖；
- 驗證任務；
- 驗證多人連線；
- 早期內容測試。

## 11.3 Compatibility Adapter

未來可建立：

```text
TMS/adapters/evennia/
```

用途：

- 匯出 CompilableWorld；
- 匯入舊 Evennia 世界；
- 支援既有 MUD；
- 作為相容層。

## 11.4 不再承擔的責任

Evennia 不再是：

- 唯一 Runtime；
- 核心資料模型；
- 唯一 UI；
- 模組治理中心；
- AI 權限核心；
- CompilableWorld 標準。

---

# 第十二章　語言與技術選擇

## 12.1 核心語言

核心 Runtime 可考慮：

- Rust；
- Python；
- 混合架構。

## 12.2 Rust 適合

- Kernel；
- Event Bus；
- State Store；
- Scheduler；
- Transaction；
- Networking；
- High-concurrency Runtime；
- Module Sandbox。

## 12.3 Python 適合

- AI Adapter；
- World Compiler；
- Data Pipeline；
- MCP；
- Skill；
- Prototype Module；
- Testing；
- Content Tooling。

## 12.4 建議混合

```text
Rust
→ Runtime Kernel

Python
→ Compiler / AI / Tooling / Early Modules

JSON / CSV / EML
→ Authoring

Web
→ UI
```

但第一版不必一開始全部 Rust 化。

可以先建立語言無關契約，再決定 Runtime 實作。

---

# 第十三章　建議專案目錄

```text
compilableworld-runtime/
├── kernel/
│   ├── entity/
│   ├── state/
│   ├── action/
│   ├── transition/
│   ├── event/
│   ├── scheduler/
│   ├── permission/
│   ├── persistence/
│   └── module-runtime/
│
├── compiler/
│   ├── loaders/
│   ├── schemas/
│   ├── validators/
│   ├── ir/
│   └── targets/
│
├── modules/
│   ├── SMS/
│   └── TMS/
│
├── gateway/
│   ├── text/
│   ├── websocket/
│   ├── http/
│   ├── agent/
│   └── test/
│
├── projections/
│   ├── player/
│   ├── combat/
│   ├── world/
│   └── admin/
│
├── ui/
│   ├── terminal/
│   ├── web/
│   ├── desktop/
│   ├── admin/
│   └── editor/
│
├── ai/
│   ├── intent-parser/
│   ├── narrative/
│   ├── npc/
│   ├── gm/
│   └── testing/
│
├── adapters/
│   ├── evennia/
│   ├── fluffos/
│   └── legacy/
│
├── worlds/
├── tests/
├── migrations/
├── observability/
└── docs/
```

---

# 第十四章　第一版最小 Runtime

## 14.1 必需 Kernel

- Entity Registry；
- State Store；
- Action IR；
- Transition Rule；
- Event Bus；
- Scheduler；
- Module Loader；
- Snapshot；
- Event Log。

## 14.2 第一批模組

```text
movement
room
inventory
door
health
basic-combat
dialogue
quest
```

## 14.3 第一個 UI

建議先保留：

```text
Terminal / Web Text UI
```

因為：

- 易於測試；
- 與 MUD 核心一致；
- 不需先完成大量前端；
- 可直接驗證 Action IR 與事件。

---

# 第十五章　開發階段

## Phase 0：架構凍結

- Kernel 責任；
- Module Contract；
- State IR；
- Action IR；
- Event IR；
- View Model；
- Permission；
- Persistence。

## Phase 1：單機最小 Runtime

- Entity；
- State；
- Action；
- Event；
- Snapshot；
- Terminal。

## Phase 2：模組系統

- Module Manifest；
- Module Loader；
- Dependency；
- Permission；
- Island Test。

## Phase 3：CompilableWorld Loader

- JSON；
- CSV；
- EML；
- Manifest；
- World IR；
- Runtime Package。

## Phase 4：Web Gateway

- WebSocket；
- Session；
- View Model；
- Browser UI。

## Phase 5：AI Action Parser

- Natural Language；
- Action IR；
- Validator；
- Narrative Renderer。

## Phase 6：多人與持久世界

- Account；
- Character；
- Concurrency；
- Conflict；
- Save；
- Replay。

## Phase 7：進階機制與 Agent

- Combat；
- Economy；
- Faction；
- AI NPC；
- GM；
- AI Player；
- World Patch。

---

# 第十六章　主要反模式

## 16.1 Kernel 內建所有玩法

會變成新的單體引擎。

## 16.2 模組直接操作資料庫

破壞權限、事件與回放。

## 16.3 UI 執行遊戲規則

造成不同 UI 出現不同世界結果。

## 16.4 AI 成為必需核心

模型服務失敗時世界無法運作。

## 16.5 CompilableWorld 綁死單一 Runtime

失去跨引擎與長期演化能力。

## 16.6 MSSP 只變成資料夾命名

真正的 MSSP 必須包含：

- 能力分層；
- 模組契約；
- 選擇性載入；
- 權限；
- 觀測；
- 孤島測試；
- 版本。

---

# 第十七章　理論意義

## 17.1 遊戲引擎從內容容器變成世界算子

傳統引擎通常以：

- 場景；
- 物件；
- 渲染；
- 物理；

為中心。

本系統則以：

- 狀態；
- 行為；
- 事件；
- 規則；
- 模組；
- 因果歷史；

為核心。

## 17.2 MUD 成為最接近世界原始碼的介面

MUD 的文字性使世界行為可被：

- 人類閱讀；
- AI 解析；
- 測試腳本呼叫；
- 事件重播；
- API 映射；
- 多 UI 投影。

因此它不是落後介面，而是最適合 CompilableWorld 的第一層可觀測執行形式。

## 17.3 UI 成為世界的投影

$$
V_i=\Pi_i(W)
$$

其中：

- $W$：同一世界狀態；
- $\Pi_i$：不同 UI 投影；
- $V_i$：文字、Web、桌面、管理介面。

世界只有一個，但可具有多個視圖。

---

# 第十八章　結論

本專案不應再以 Evennia Fork 作為主要核心。

這並不是否定 Evennia，而是因為專案已經從：

> 建立一個 AI MUD

演化為：

> 建立一個以 MUD 為第一介面的 MSSP 模組化可編譯世界執行引擎。

新的核心架構應為：

```text
World Sources
→ World Adaptation
→ JSON / CSV / EML
→ CompilableWorld
→ World IR
→ World Kernel
→ MSSP Mechanism Modules
→ Event / State / View Model
→ Multiple UI
```

Evennia 應保留為：

- 參考實作；
- 原型工具；
- 相容 Adapter；
- 舊 MUD 匯入與輸出目標。

最終原則為：

> Kernel 只執行世界；模組定義玩法；CompilableWorld 定義世界；UI 呈現世界；AI 理解與擴張世界。

只有在這五者真正解耦後，專案才有能力從一款 MUD，擴張為可支援多種遊戲、Agent 社會與長期數位世界的通用 Runtime。

---

# 附錄 A　最小模組契約

```yaml
module:
  id: inventory.core
  version: 0.1.0
  architecture: MSSP
  layer: TMS

requires:
  kernel:
    - entity
    - state
    - action
    - event

provides:
  states:
    - inventory.items
    - inventory.capacity

  actions:
    - inventory.take
    - inventory.drop
    - inventory.transfer

  events:
    - inventory.item_added
    - inventory.item_removed

permissions:
  read:
    - entity.location
    - inventory.*
  write:
    - inventory.*

tests:
  - take_item
  - drop_item
  - capacity_limit
  - concurrent_transfer
```

---

# 附錄 B　最小 View Model

```yaml
view_model:
  type: player_inventory
  version: 1

  actor: player_001

  capacity:
    current: 7
    max: 12

  items:
    - id: item_old_key
      name: 古老鑰匙
      quantity: 1
      actions:
        - inspect
        - use
        - drop
```

---

# 附錄 C　重構檢查清單

- [ ] Evennia 不再是 Canonical Runtime
- [ ] World IR 不依賴 Evennia Object
- [ ] State Store 有統一寫入入口
- [ ] Action 有完整生命週期
- [ ] 所有模組修改以 Delta 提交
- [ ] 所有跨模組協作以 Event 完成
- [ ] UI 不執行核心規則
- [ ] AI 不直接寫入 Runtime
- [ ] 模組具備 Manifest 與 Permission
- [ ] TMS 可進行 Island Test
- [ ] Runtime 可在沒有 AI 時運作
- [ ] Evennia 僅存在於 Adapter 或 Prototype
- [ ] Snapshot 與 Event Replay 可用
- [ ] CompilableWorld 可輸出 Runtime Package
- [ ] Terminal 與 Web UI 可共享同一世界狀態
