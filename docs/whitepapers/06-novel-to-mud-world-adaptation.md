---
title: "Novel-to-MUD World Adaptation：大型世界觀離線改編、世界種子包與遊戲內局部生成架構"
subtitle: "從高 Token 原作理解到 JSON／CSV／EML 世界種子、CompilableWorld 與受限 Runtime AI"
author: "Neo.K / EVEMISSLAB"
version: "v0.1"
status: "技術架構論文草案"
date: "2026-07-13"
language: "zh-TW"
keywords:
  - Novel-to-MUD
  - World Adaptation
  - World Seed Package
  - CompilableWorld
  - JSON
  - CSV
  - EML
  - MSSP Skill
  - MCP
  - AI Agent
  - MUD
  - Token Optimization
---

# Novel-to-MUD World Adaptation：大型世界觀離線改編、世界種子包與遊戲內局部生成架構

## 摘要

本文提出一套專門將小說、長篇世界觀設定、角色資料、歷史年表與既有敘事作品，轉換為可供 MUD、CompilableWorld 與 AI 世界狀態機使用之結構化世界種子包的離線改編架構。

大型小說若在遊戲執行期間被反覆交由 AI 重新閱讀與理解，將造成極高 Token 消耗、回應延遲、世界事實漂移、角色重複、設定衝突與不可重現等問題。即使現代大型語言模型具有長上下文能力，也不代表將完整作品持續載入 Runtime 是合理的遊戲工程方案。

因此，本文主張將 AI 使用分為兩個階段：

1. **離線大型世界觀改編階段**：使用專門的 MSSP Skill、MCP、Agent 工作流、本地模型或雲端 API，一次性或增量地把原作轉換為 JSON、CSV、EML、Manifest、索引、來源追蹤與驗證報告；
2. **遊戲內局部生成階段**：只載入當前區域、角色、任務、事件、規則與玩家歷史，在已編譯世界中生成局部對話、事件、細節與小規模世界 Patch。

完整流程為：

$$
T_{\mathrm{source}}
\xrightarrow{\mathcal{I}}
C_{\mathrm{source}}
\xrightarrow{\mathcal{X}}
K_{\mathrm{canon}}
\xrightarrow{\mathcal{A}}
W_{\mathrm{adapted}}
\xrightarrow{\mathcal{S}}
P_{\mathrm{seed}}
\xrightarrow{\mathcal{C}}
W_{\mathrm{compiled}}
\xrightarrow{\mathcal{R}}
W_{\mathrm{runtime}}
$$

其中：

- $T_{\mathrm{source}}$：小說、設定集、年表、角色資料與補充文本；
- $\mathcal{I}$：來源匯入與分段；
- $C_{\mathrm{source}}$：可索引來源語料；
- $\mathcal{X}$：實體、事件、關係、公理與時間線抽取；
- $K_{\mathrm{canon}}$：原作知識層；
- $\mathcal{A}$：遊戲化改編算子；
- $W_{\mathrm{adapted}}$：可遊戲化世界模型；
- $\mathcal{S}$：種子包封裝；
- $P_{\mathrm{seed}}$：World Seed Package；
- $\mathcal{C}$：CompilableWorld 編譯；
- $W_{\mathrm{compiled}}$：已驗證世界；
- $\mathcal{R}$：Runtime 載入；
- $W_{\mathrm{runtime}}$：實際遊戲世界。

本文的核心結論是：

> 大型模型負責一次性或增量地把作品改編成可計算世界；遊戲內模型只負責在已計算世界中進行局部生成與受控擴張。

---

# 第一章　問題提出

## 1.1 長篇小說不適合直接進入遊戲 Runtime

若遊戲內 AI 每次都重新讀取完整小說，將遇到以下問題：

- Token 成本高；
- 延遲高；
- 同一設定可能被不同次呼叫重新解釋；
- 人名與別名容易重複；
- 世界公理與角色信念容易混淆；
- 原作事實與遊戲新增內容混合；
- 無法穩定版本化；
- 無法可靠重播；
- 難以測試；
- 難以跨引擎使用。

因此：

$$
K_{\mathrm{runtime}}
\neq
K_{\mathrm{entire\ source}}
$$

合理的 Runtime 上下文應為：

$$
K_{\mathrm{runtime}}
=
K_{\mathrm{global\ minimal}}
+
K_{\mathrm{region}}
+
K_{\mathrm{scene}}
+
K_{\mathrm{actors}}
+
K_{\mathrm{task}}
+
K_{\mathrm{player\ history}}
$$

---

## 1.2 世界抽取不等於世界改編

將小說中的人名、地點與事件抽取出來，只能得到知識庫，不能直接得到遊戲。

小說通常缺少：

- 完整地圖；
- 經濟參數；
- 戰鬥數值；
- NPC 日常狀態；
- 可重複任務；
- 非主角視角；
- 可執行規則；
- 玩家失敗路徑；
- 世界回應機制。

因此需要區分：

$$
W_{\mathrm{novel}}
\xrightarrow{\mathcal{E}}
K_{\mathrm{canon}}
\xrightarrow{\mathcal{A}}
W_{\mathrm{game}}
$$

其中：

- $\mathcal{E}$：原作抽取；
- $\mathcal{A}$：遊戲化改編。

---

# 第二章　雙階段 AI 架構

## 2.1 第一階段：離線世界觀改編

```text
小說／設定集／角色資料
→ 來源匯入
→ 章節分段
→ 實體解析
→ 關係整合
→ 時間線重建
→ 世界公理抽取
→ 遊戲化改編
→ JSON／CSV／EML
→ 驗證
→ World Seed Package
```

此階段特徵：

- 可使用大量 Token；
- 不要求即時；
- 可使用多模型；
- 可人工審查；
- 可反覆修正；
- 可保存中間產物；
- 可增量處理；
- 可在本地或雲端執行。

---

## 2.2 第二階段：遊戲內局部生成

```text
World Seed Package
→ CompilableWorld
→ State IR／Action IR／Event IR
→ Runtime
→ 局部 AI
→ 對話／事件／任務／敘事／小型 Patch
```

此階段特徵：

- 低延遲；
- 上下文受限；
- 只讀必要資料；
- 不重新理解整部作品；
- 不直接改寫世界公理；
- 所有重要修改需形成 Patch。

---

## 2.3 雙階段責任分離

| 項目 | 離線改編 AI | 遊戲內 AI |
|---|---|---|
| 閱讀完整小說 | 是 | 否 |
| 建立角色唯一 ID | 是 | 否 |
| 建立時間線 | 是 | 局部讀取 |
| 建立世界公理 | 是 | 不可直接修改 |
| 建立地圖骨架 | 是 | 可局部擴張 |
| 建立遊戲規則 | 是 | 依規則執行 |
| 即時 NPC 對話 | 否 | 是 |
| 玩家行為解析 | 否 | 是 |
| 局部事件生成 | 可預生成 | 是 |
| 世界大規模重構 | 是 | 否 |
| 直接寫入正式世界 | 否 | 否，需 Patch |

---

# 第三章　Novel-to-MUD World Adaptation System

## 3.1 系統定義

$$
\mathcal{N}
=
(
I,
G,
E,
R,
T,
A,
V,
P
)
$$

其中：

- $I$：Ingestion，來源匯入；
- $G$：Segmentation，分段與索引；
- $E$：Extraction，實體與事件抽取；
- $R$：Resolution，實體消歧與合併；
- $T$：Timeline and Topology，時間線與空間拓撲；
- $A$：Adaptation，遊戲化改編；
- $V$：Validation，驗證；
- $P$：Packaging，種子包封裝。

---

## 3.2 它不是單一 LLM 呼叫

$$
\mathrm{WorldAdaptationSystem}
\neq
\mathrm{SinglePrompt}
$$

更完整地說：

$$
\mathrm{WorldAdaptationSystem}
=
\mathrm{Skill}
+
\mathrm{Router}
+
\mathrm{Storage}
+
\mathrm{Schemas}
+
\mathrm{Validators}
+
\mathrm{Models}
+
\mathrm{HumanReview}
$$

---

# 第四章　來源匯入與分段

## 4.1 來源類型

系統應支援：

- TXT；
- Markdown；
- DOCX；
- EPUB；
- PDF；
- HTML；
- JSON；
- CSV；
- 世界觀百科；
- 角色卡；
- 年表；
- 地圖說明；
- 舊 MudLib；
- 人工筆記。

---

## 4.2 分段原則

不可只依固定 Token 長度切分。

應考慮：

- 章；
- 節；
- 場景；
- 視角人物；
- 時間跳轉；
- 地點切換；
- 事件完整性；
- 對話群；
- 設定說明；
- 附錄。

---

## 4.3 分段單元

```yaml
chunk:
  id: chapter_012_scene_004
  source_file: novel.md
  chapter: 12
  scene: 4
  viewpoint: li_heng
  location: gray_crown_palace
  time_hint: winter_year_18
  start_offset: 182442
  end_offset: 188731
```

---

# 第五章　實體抽取與消歧

## 5.1 實體類型

- Character；
- Faction；
- Location；
- Item；
- Species；
- Ability；
- Rule；
- Event；
- Concept；
- Organization；
- Title；
- Resource。

---

## 5.2 別名與同一性

同一角色可能被稱為：

```text
李衡
三殿下
王子
黑衣青年
北境之狼
```

必須解析為：

```yaml
entity:
  id: character_li_heng
  canonical_name: 李衡
  aliases:
    - 三殿下
    - 王子
    - 黑衣青年
    - 北境之狼
```

---

## 5.3 實體解析函數

$$
\mathcal{R}
:
\{m_1,m_2,\ldots,m_n\}
\rightarrow
e_i
$$

其中 $m_i$ 是文本提及，$e_i$ 是唯一實體。

系統應保存：

- 合併理由；
- 信心；
- 衝突；
- 人工覆核結果。

---

# 第六章　原作知識層

## 6.1 三層 Canon

### Source Canon

原作明確表述。

```yaml
type: source_canon
value: 王城禁止公開施法
source_ref: chapter_12_scene_04
confidence: 1.0
```

### Adapted Canon

為遊戲可執行性作出的改編。

```yaml
type: adapted_canon
value: 王城公開施法會增加法律警戒值
derived_from:
  - chapter_12_scene_04
adaptation_reason: 將敘事禁令轉換為遊戲規則
```

### Generated Expansion

遊戲運行後新增。

```yaml
type: generated_expansion
value: 北門成立反魔法巡邏隊
source_event: event_8841
world_version: 0.8.2
```

---

## 6.2 角色信念與世界事實

$$
B_{\mathrm{character}}
\neq
F_{\mathrm{world}}
$$

例如：

```yaml
claim:
  value: 黑潮是神罰
  speaker: priest_001
  epistemic_status: belief
  world_truth_status: unresolved
```

若不區分，AI 可能把角色偏見錯誤編譯為世界公理。

---

# 第七章　時間線重建

## 7.1 小說時間不一定線性

可能存在：

- 倒敘；
- 插敘；
- 多視角；
- 不可靠敘述；
- 模糊年代；
- 同時事件；
- 傳聞事件。

---

## 7.2 時間線事件

```yaml
event:
  id: event_fall_of_north_gate
  title: 北門陷落
  time:
    absolute: null
    relative_to: event_black_tide_arrival
    offset_days: -3
  participants:
    - faction_north_guard
    - faction_black_tide
  locations:
    - north_gate
  epistemic_status: confirmed
```

---

## 7.3 時間圖

$$
G_T=(E,R_T)
$$

關係包括：

```text
before
after
during
overlaps
causes
reported_after
uncertain
```

---

# 第八章　地理與世界拓撲

## 8.1 小說地點不是完整遊戲地圖

原作可能只說：

> 他穿過王城，半日後抵達北門。

這不足以生成所有房間。

改編 Agent 需要建立：

- Region；
- Zone；
- Location；
- Room；
- Exit；
- Travel Edge；
- Hidden Connection；
- Access Condition。

---

## 8.2 地理資料分級

### Canon Location

原作明確存在。

### Inferred Location

由敘事關係推導。

### Gameplay Location

為可玩性新增。

```yaml
location:
  id: room_gray_crown_market_east
  source_type: gameplay_adaptation
  parent: gray_crown_market
  reason: 提供商業與任務節點
```

---

# 第九章　遊戲化改編算子

## 9.1 定義

$$
\mathcal{A}
:
K_{\mathrm{canon}}
\rightarrow
W_{\mathrm{playable}}
$$

它不只是摘要，而是把敘事轉為可執行世界。

---

## 9.2 主要改編工作

### 線性劇情轉任務圖

$$
G_{\mathrm{plot}}
\rightarrow
G_{\mathrm{quest}}
$$

### 能力描述轉規則

```text
他的劍快得看不見
```

不能直接變成無限速度，而應建立：

- 速度加成；
- 命中；
- 先制；
- 體力消耗；
- 條件；
- 反制方式。

### 角色命運轉狀態機

```text
敵對
→ 暫時合作
→ 懷疑
→ 背叛
→ 和解
```

### 場景描寫轉互動環境

- 可移動物；
- 可破壞物；
- 可躲藏處；
- 可聽見範圍；
- 光照；
- 門鎖；
- 危險。

---

## 9.3 改編不應偽裝成原作

每個新增資料應標記：

```text
explicit_canon
inferred_canon
gameplay_adaptation
runtime_generation
human_override
```

---

# 第十章　World Seed Package

## 10.1 定義

World Seed Package 是：

> 將原作知識、遊戲化改編、世界規則、來源索引、結構化資料與驗證結果封裝為可被 CompilableWorld 載入的標準世界胚胎。

---

## 10.2 建議目錄

```text
world-seed/
├── manifest.json
├── world.json
├── axioms.json
├── timeline.json
├── adaptation_policy.json
│
├── data/
│   ├── characters.csv
│   ├── factions.csv
│   ├── items.csv
│   ├── skills.csv
│   ├── relations.csv
│   └── localization.csv
│
├── geography/
│   ├── regions.json
│   ├── locations.csv
│   ├── rooms.csv
│   └── exits.csv
│
├── quests/
│   ├── main.json
│   ├── side.json
│   └── state_machines.json
│
├── rules/
│   ├── combat.json
│   ├── economy.json
│   ├── law.json
│   └── magic.eml
│
├── summaries/
│   ├── global_summary.md
│   ├── chapter_summaries/
│   ├── character_summaries/
│   └── region_summaries/
│
├── indexes/
│   ├── entity_index.json
│   ├── alias_index.json
│   ├── relation_index.json
│   ├── timeline_index.json
│   └── source_index.json
│
├── provenance/
│   ├── source_map.json
│   ├── extraction_log.json
│   ├── adaptation_log.json
│   ├── model_usage.json
│   └── uncertainty_report.json
│
├── schemas/
├── validation/
└── patches/
```

---

## 10.3 種子包不是完整世界

種子包應足以：

- 建立初始世界；
- 解析主要實體；
- 提供核心規則；
- 支援局部生成；
- 追溯來源；
- 持續擴張。

但它不需要預先生成：

- 每一句 NPC 對話；
- 每一個普通房間細節；
- 每一個隨機事件；
- 所有玩家分支；
- 所有未來歷史。

---

# 第十一章　Manifest 與編譯入口

## 11.1 示例

```json
{
  "seed_id": "black_tide_seed",
  "seed_version": "0.1.0",
  "source_work": {
    "title": "黑潮之城",
    "rights_status": "user_declared"
  },
  "schema_version": "0.1.0",
  "adaptation_version": "0.1.0",
  "targets": [
    "compilableworld",
    "evennia"
  ],
  "sources": {
    "world": "world.json",
    "characters": "data/characters.csv",
    "locations": "geography/locations.csv",
    "quests": "quests/main.json",
    "rules": [
      "rules/combat.json",
      "rules/magic.eml"
    ]
  },
  "validation": {
    "strict": true,
    "require_provenance": true
  }
}
```

---

# 第十二章　MCP、Skill 與 Agent 編排

## 12.1 MCP 的角色

MCP 可以提供：

- 檔案讀取；
- 文件切分；
- 向量索引；
- 資料庫；
- Schema 驗證；
- Git；
- 編譯器；
- World Seed 匯出；
- 人工審查介面。

---

## 12.2 MSSP Skill 的角色

MSSP Skill 應管理：

```text
FMS：定義世界改編系統
SCL：定義來源、權限與風險
SMS：匯入、抽取、解析、改編、驗證、封裝
TMS：小說類型、引擎、模型與特定規則
DMS：Token、錯誤、衝突、來源與品質報告
Router：只載入當前改編階段
Runtime：模型、檔案、資料庫與編譯工具
```

---

## 12.3 建議 SMS

```text
source-ingestion
segmentation
entity-extraction
entity-resolution
timeline-reconstruction
relation-graph
axiom-extraction
geography-adaptation
gameplay-adaptation
seed-packaging
validation
human-review
```

---

# 第十三章　模型與 API 無關性

## 13.1 多種生成模式

系統應支援：

```text
官方 API
使用者自帶 API Key
本地模型
外部 Agent
人工 JSON／CSV
混合模式
```

---

## 13.2 模型無關契約

$$
M_i(T)
\rightarrow
P_{\mathrm{seed}}
$$

不同模型可以採不同過程，但最後必須符合相同 World Seed Package 規格。

遊戲 Runtime 不應知道：

- 世界由哪個模型生成；
- 使用哪個聊天平台；
- 使用多少次呼叫；
- 是人工還是 AI 完成。

Runtime 只驗證種子包契約。

---

# 第十四章　Token 與成本控制

## 14.1 成本模型

$$
C_{\mathrm{adapt}}
=
C_{\mathrm{ingestion}}
+
C_{\mathrm{extraction}}
+
C_{\mathrm{resolution}}
+
C_{\mathrm{adaptation}}
+
C_{\mathrm{validation}}
$$

---

## 14.2 降低重複成本

- 分段雜湊；
- 增量重跑；
- 中間結果快取；
- 只重做失敗階段；
- 實體索引重用；
- 摘要分層；
- 模型路由；
- 小模型先抽取；
- 大模型處理衝突；
- 人工鎖定已確認 Canon。

---

## 14.3 增量改編

若只增加一章：

```text
新章節
→ 分段
→ 新實體抽取
→ 舊實體解析
→ 時間線增量
→ 衝突檢查
→ Seed Patch
```

不應重新處理整本小說。

---

# 第十五章　品質與驗證

## 15.1 結構驗證

- JSON Schema；
- CSV Schema；
- ID 唯一；
- 檔案完整；
- Manifest 路徑；
- 編碼。

---

## 15.2 世界驗證

- 實體重複；
- 別名衝突；
- 時間矛盾；
- 地點不可達；
- 角色同時出現在不可能地點；
- 能力規則衝突；
- 任務不可完成；
- 公理互斥。

---

## 15.3 改編品質

每個改編項目可包含：

```yaml
adaptation_quality:
  canon_fidelity: 0.92
  gameplay_necessity: 0.88
  uncertainty: 0.14
  human_review: approved
```

---

# 第十六章　遊戲內局部 AI

## 16.1 局部上下文包

```yaml
runtime_context:
  global_axioms:
    - magic_requires_memory
    - death_is_persistent

  region:
    id: gray_crown

  scene:
    id: south_gate

  actors:
    - player_001
    - guard_001

  active_quests:
    - quest_black_tide_001

  recent_events:
    - event_8840
    - event_8841
```

---

## 16.2 Runtime AI 可以做

- 解析玩家自然語言；
- 生成 NPC 回應；
- 生成局部敘事；
- 提議小型事件；
- 產生低風險房間細節；
- 建立受控 Patch；
- 根據狀態生成任務變體。

---

## 16.3 Runtime AI 不可以做

- 重新定義整個原作；
- 任意改世界公理；
- 改寫已確認 Canon；
- 建立沒有來源或理由的大型歷史；
- 直接覆蓋 Seed；
- 無審查修改核心規則。

---

# 第十七章　資料版本

至少需要：

```text
Source Version
Extraction Version
Canon Version
Adaptation Version
Seed Version
Schema Version
Compiler Version
World Version
Runtime Version
Save Version
```

形式上：

$$
V_{\mathrm{world}}
=
(
v_s,
v_e,
v_c,
v_a,
v_p,
v_i,
v_r
)
$$

---

# 第十八章　第一版 MVP

## 18.1 輸入

- 一份 Markdown 小說；
- 一份世界觀設定；
- 一份角色表。

---

## 18.2 輸出

```text
manifest.json
world.json
axioms.json
characters.csv
factions.csv
locations.csv
relations.csv
timeline.json
quests.json
source_map.json
uncertainty_report.json
```

---

## 18.3 第一版流程

```text
Source
→ Chunk
→ Extract
→ Resolve
→ Build Timeline
→ Build Relations
→ Adapt Geography
→ Adapt Quests
→ Export Seed
→ Validate
```

---

# 第十九章　開發階段

## Phase 0：Seed Specification

- 定義目錄；
- 定義 Manifest；
- 定義 Schema；
- 定義 Canon 類型；
- 定義來源追蹤。

## Phase 1：來源匯入

- Markdown；
- TXT；
- DOCX；
- 分段；
- 雜湊；
- 索引。

## Phase 2：實體與關係

- 抽取；
- 別名；
- 合併；
- 關係圖；
- 衝突報告。

## Phase 3：時間與地理

- 時間線；
- Region；
- Location；
- Room Seed；
- Travel Graph。

## Phase 4：遊戲化改編

- 任務；
- 狀態機；
- 規則；
- 能力；
- 經濟；
- NPC 原型。

## Phase 5：CompilableWorld

- World IR；
- State IR；
- Action IR；
- Event IR；
- 編譯；
- Evennia Adapter。

## Phase 6：局部 Runtime AI

- Context Router；
- NPC；
- GM；
- Action Parser；
- Patch。

---

# 第二十章　反模式

## 20.1 每次遊戲都讀整本小說

成本高、延遲高且不可重現。

## 20.2 一次提示生成整個世界

缺少中間結果、驗證與失敗重試。

## 20.3 逐章生成但不做實體解析

同一角色會被重複建立。

## 20.4 把摘要當世界資料

摘要不能取代 ID、關係、規則與時間線。

## 20.5 把 AI 推測當 Canon

必須標記來源與不確定性。

## 20.6 Runtime 直接修改 Seed

會破壞來源、版本與回滾。

## 20.7 綁死單一模型

模型更換時整套系統失效。

---

# 第二十一章　理論意義

## 21.1 小說改編成世界是一種編譯

$$
\text{Narrative}
\rightarrow
\text{World Model}
\rightarrow
\text{Executable World}
$$

這不只是內容生成，而是跨表示轉換。

---

## 21.2 世界種子是敘事與執行的中介

World Seed Package 同時保留：

- 原作來源；
- 遊戲改編；
- 結構化資料；
- 可編譯契約；
- 未來擴張空間。

---

## 21.3 AI 從即時幻想者轉為世界工程工具

AI 的主要價值不是每次即興重寫世界，而是：

- 建立結構；
- 消解歧義；
- 補足缺口；
- 產生規則；
- 驗證一致性；
- 壓縮 Runtime 上下文。

---

# 第二十二章　結論

大型小說與世界觀不應直接進入遊戲 Runtime。

正確架構是：

```text
小說／世界觀
→ 專用離線改編 Agent
→ JSON／CSV／EML／Manifest
→ World Seed Package
→ CompilableWorld
→ State IR／Action IR／Event IR
→ Evennia／未來 Runtime
→ 遊戲內局部 AI
```

其核心原則為：

> 一次理解，結構化保存；局部載入，長期運行。

這樣可以同時降低：

- Token；
- 延遲；
- 世界漂移；
- 實體重複；
- 設定矛盾；
- Runtime 複雜度。

並提高：

- 可維護性；
- 可測試性；
- 可版本化；
- 可追溯性；
- 可跨模型；
- 可跨引擎；
- 可人工審查；
- 可持續擴張。

因此，CompilableWorld 前方真正需要的不是另一個遊戲內聊天 AI，而是：

> **Novel-to-MUD World Adaptation Skill System。**

它是大型敘事作品進入可計算世界之前的專用離線編譯前端。

---

# 附錄 A　最小 World Seed Manifest

```json
{
  "seed_id": "demo_seed",
  "seed_version": "0.1.0",
  "schema_version": "0.1.0",
  "source": {
    "title": "Demo Novel",
    "version": "1.0",
    "rights_status": "user_owned"
  },
  "targets": [
    "compilableworld",
    "evennia"
  ],
  "files": {
    "world": "world.json",
    "axioms": "axioms.json",
    "characters": "data/characters.csv",
    "locations": "geography/locations.csv",
    "relations": "data/relations.csv",
    "timeline": "timeline.json",
    "quests": "quests/main.json",
    "provenance": "provenance/source_map.json"
  }
}
```

---

# 附錄 B　來源追蹤示例

```yaml
record:
  id: adapted_rule_city_magic_ban
  output_file: rules/law.json
  output_path: /rules/0

  source:
    file: novel.md
    chunk: chapter_12_scene_04
    quote_hash: sha256:example

  classification: gameplay_adaptation
  model: external_agent
  confidence: 0.93
  human_review: pending
```

---

# 附錄 C　第一版實作清單

- [ ] World Seed Package Specification
- [ ] Source Chunk Schema
- [ ] Entity Schema
- [ ] Alias Index
- [ ] Relation Schema
- [ ] Timeline Schema
- [ ] Canon Classification
- [ ] Adaptation Log
- [ ] Source Map
- [ ] Uncertainty Report
- [ ] JSON Export
- [ ] CSV Export
- [ ] EML Rule Export
- [ ] Manifest Builder
- [ ] Validator
- [ ] Incremental Patch
- [ ] CompilableWorld Loader
- [ ] Evennia Seed Importer
