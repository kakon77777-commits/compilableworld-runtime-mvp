---
title: "CompilableWorld 的前置資料層：JSON、CSV、Manifest 與可維護世界資料架構"
subtitle: "從人類—AI 共編資料到可驗證、可編譯、可遷移的世界來源層"
author: "Neo.K / EVEMISSLAB"
version: "v0.1"
status: "技術架構草案"
date: "2026-07-13"
language: "zh-TW"
keywords:
  - CompilableWorld
  - JSON
  - CSV
  - World IR
  - EML
  - Manifest
  - Schema
  - AI Agent
  - Evennia
  - Data Authoring
---

# CompilableWorld 的前置資料層：JSON、CSV、Manifest 與可維護世界資料架構

## 摘要

本文提出 CompilableWorld 在正式完成之前，乃至完成之後，仍應保留 JSON、CSV 與 Manifest 作為人類與 AI 可共同維護之世界來源層的技術架構。

CompilableWorld 的目標，是將小說、世界觀設定、規則、角色、地圖、任務、經濟與事件等異質資料，轉換為可驗證、可編譯、可執行、可版本化及可遷移的世界結構。然而，若人類與 AI 直接操作最終 Runtime IR、底層資料庫物件或引擎內部類別，將導致資料可讀性下降、維護門檻提高、批次修改困難、格式演化僵化，以及來源與執行狀態混淆等問題。

因此，本文主張：

> JSON 與 CSV 不應被視為 CompilableWorld 尚未完成前的臨時替代方案，而應被正式定位為 Authoring Layer，也就是人類與 AI 共同編輯、審查、批次處理與版本控制的來源資料層。

整體架構如下：

$$
T_{\mathrm{natural}}
\rightarrow
A_{\mathrm{JSON/CSV}}
\rightarrow
N_{\mathrm{normalized}}
\rightarrow
V_{\mathrm{validated}}
\rightarrow
W_{\mathrm{IR}}
\rightarrow
C_{\mathrm{world}}
\rightarrow
R_{\mathrm{runtime}}
$$

其中：

- $T_{\mathrm{natural}}$：小說、設定、提示與人工輸入；
- $A_{\mathrm{JSON/CSV}}$：可維護來源資料；
- $N_{\mathrm{normalized}}$：正規化資料；
- $V_{\mathrm{validated}}$：通過結構、型別、依賴與規則驗證的資料；
- $W_{\mathrm{IR}}$：世界中間表示；
- $C_{\mathrm{world}}$：CompilableWorld 編譯結果；
- $R_{\mathrm{runtime}}$：Evennia、Rust Runtime、瀏覽器世界或其他目標引擎。

本文進一步定義 JSON、CSV、Manifest、Schema、資料庫、CompilableWorld 與 Runtime 各自的責任，避免同一份資料在多個位置同時成為「真實來源」。同時提出 ID 命名空間、來源追蹤、資料雜湊、編譯順序、錯誤隔離、版本遷移與 AI 批次維護等規格。

**關鍵詞：** CompilableWorld、JSON、CSV、Manifest、World IR、EML、AI Agent、資料來源層、版本控制、世界編譯

---

# 第一章　問題提出

## 1.1 CompilableWorld 不能直接等同於人類編輯格式

CompilableWorld 最終應服務：

- 世界驗證；
- 跨引擎編譯；
- 執行時載入；
- 規則依賴；
- 存檔遷移；
- AI 世界修改；
- 多版本世界治理。

但這不代表 CompilableWorld 的內部格式適合由人類直接維護。

底層可執行格式通常會出現：

- 高度正規化；
- 大量引用 ID；
- 編譯器專用欄位；
- 快取；
- 索引；
- 引擎能力映射；
- 版本內部資訊；
- 冗長的型別標記；
- 不適合手工編輯的序列化結構。

若人類與 AI 直接操作此層，將使世界編輯等同於直接修改編譯產物。

這與直接修改二進位檔或資料庫內部索引類似，不是合理的長期維護方式。

## 1.2 實作中自然出現的需求

在實際建立世界時，開發者往往很快發現：

- 大量角色適合表格；
- 大量物品適合表格；
- 技能數值需要批次比較；
- 地圖房間需要大量 ID；
- 任務與公理需要巢狀結構；
- 世界來源需要保存人工說明；
- AI 需要能批次生成與修正；
- Git Diff 必須保持可讀；
- 非程式開發者需要參與。

因此，單一格式無法同時滿足所有需求。

JSON 與 CSV 的混合使用，並不是架構妥協，而是對資料形態差異的承認。

---

# 第二章　正式定位：Authoring Layer

## 2.1 定義

本文將 JSON／CSV 來源層定義為：

> 位於自然語言來源與 CompilableWorld 中間表示之間，供人類、AI、編輯器、版本控制與批次工具共同操作的世界資料編輯層。

其形式為：

$$
A_W
=
J_W
\cup
C_W
\cup
M_W
\cup
S_W
$$

其中：

- $J_W$：JSON 結構資料；
- $C_W$：CSV 表格資料；
- $M_W$：Manifest 與來源索引；
- $S_W$：Schema 與契約。

## 2.2 Authoring Format 與 Canonical Runtime Format

應明確區分：

### Authoring Format

供人類與 AI 編輯：

```text
JSON
CSV
Markdown
EML
Manifest
```

### Canonical Intermediate Format

供驗證與編譯：

```text
Normalized World IR
Typed Graph
Resolved References
Validated Rules
```

### Runtime Format

供遊戲執行：

```text
Evennia Objects
Database Rows
Compiled Rust Structures
Runtime Cache
Event State
```

因此：

$$
A_W
\neq
W_{\mathrm{IR}}
\neq
R_W
$$

但三者可透過明確轉換函數連接：

$$
f_{\mathrm{normalize}}
:
A_W
\rightarrow
W_{\mathrm{IR}}
$$

$$
f_{\mathrm{compile}}
:
W_{\mathrm{IR}}
\rightarrow
R_W
$$

---

# 第三章　JSON 的責任範圍

## 3.1 適合 JSON 的資料

JSON 適合表示具有以下性質的資料：

- 巢狀；
- 欄位可選；
- 結構不規則；
- 需要 metadata；
- 需要 provenance；
- 具有多層關係；
- 需要條件或狀態機；
- 不適合表格展開。

建議使用 JSON 的內容：

```text
world.json
manifest.json
axioms.json
relations.json
quests.json
events.json
factions.json
rule_sets.json
generation_profiles.json
version_map.json
```

## 3.2 世界主檔

```json
{
  "world_id": "black_tide",
  "title": "黑潮之城",
  "version": "0.1.0",
  "schema_version": "0.1.0",
  "genre": [
    "dark_fantasy",
    "political"
  ],
  "default_language": "zh-TW",
  "axiom_files": [
    "axioms/core.json"
  ],
  "source_manifest": "manifest.json"
}
```

## 3.3 任務適合使用 JSON

任務通常具有狀態、條件與分支：

```json
{
  "quest_id": "quest_black_tide_001",
  "title": "黑潮前兆",
  "states": [
    "unavailable",
    "available",
    "accepted",
    "completed",
    "failed"
  ],
  "requirements": {
    "character_level_min": 2,
    "required_flags": [
      "met_south_gate_guard"
    ]
  },
  "branches": [
    {
      "when": "player.faction == 'guard'",
      "next": "guard_route"
    },
    {
      "when": "player.faction == 'cult'",
      "next": "cult_route"
    }
  ]
}
```

若硬塞入 CSV，會產生大量重複欄位、巢狀 JSON 字串、不易讀取的條件欄，並失去表格優勢。

---

# 第四章　CSV 的責任範圍

## 4.1 適合 CSV 的資料

CSV 適合：

- 大量同型資料；
- 固定欄位；
- 數值平衡；
- 人工批次編輯；
- 試算表操作；
- 排序與篩選；
- 翻譯；
- 大量 ID 管理。

建議使用 CSV 的內容：

```text
characters.csv
items.csv
skills.csv
rooms.csv
exits.csv
loot_tables.csv
recipes.csv
shops.csv
localization.csv
balance_parameters.csv
```

## 4.2 角色表

```csv
character_id,name,role,faction,region,level,unique,persistence
npc_guard_001,沉默守衛,guard,gray_crown_guard,gray_crown,3,true,persistent
npc_merchant_001,雜貨商,merchant,civilian,gray_crown,1,false,regenerable
npc_refugee_001,流亡者,refugee,none,south_camp,1,false,delta
```

此格式便於以試算表排序、大量複製、AI 批次生成、人工檢查缺失欄位、調整數值與進行翻譯。

## 4.3 房間與出口應分表

`rooms.csv`：

```csv
room_id,name,region,description_key,danger_level,persistence
room_south_gate,灰冠城南門,gray_crown,room.south_gate.desc,1,persistent
room_market,灰冠市集,gray_crown,room.market.desc,1,persistent
```

`exits.csv`：

```csv
exit_id,from_room,to_room,direction,bidirectional,condition
exit_001,room_south_gate,room_market,north,true,
exit_002,room_market,room_hidden_vault,down,false,has_key:old_vault_key
```

這比在每個房間 JSON 裡重複寫出口，更適合大型地圖批次維護。

---

# 第五章　Manifest：世界資料的總索引

## 5.1 Manifest 的必要性

當資料散布在多個 JSON 與 CSV 中，系統需要一個唯一入口。

Manifest 負責回答：

- 哪些檔案屬於這個世界？
- 每個檔案使用何種 Schema？
- 編譯順序為何？
- ID 命名空間是什麼？
- 目標 Runtime 是什麼？
- 依賴哪些模組？
- 哪些檔案可選？
- 各檔案雜湊為何？
- 哪些來源由 AI 生成？
- 哪些來源由人類審查？

## 5.2 Manifest 示例

```json
{
  "world_id": "black_tide",
  "world_version": "0.1.0",
  "schema_version": "0.1.0",
  "namespace": "bt",
  "compiler_version": "0.1.0",
  "targets": [
    "evennia"
  ],
  "sources": {
    "world": "world.json",
    "axioms": [
      "axioms/core.json"
    ],
    "characters": [
      "data/characters.csv"
    ],
    "items": [
      "data/items.csv"
    ],
    "rooms": [
      "maps/rooms.csv"
    ],
    "exits": [
      "maps/exits.csv"
    ],
    "quests": [
      "quests/main_quests.json"
    ],
    "localization": [
      "localization/zh-TW.csv"
    ]
  },
  "dependencies": [
    {
      "module": "core-combat",
      "version": ">=0.1,<1.0"
    }
  ],
  "build": {
    "strict": true,
    "fail_on_warning": false
  }
}
```

## 5.3 Manifest 是唯一編譯入口

編譯器不應任意掃描整個資料夾後猜測哪些檔案要載入。

應採：

```text
manifest.json
→ Resolve Sources
→ Validate Paths
→ Validate Hashes
→ Load Schemas
→ Normalize
→ Compile
```

這樣才能可重現、可審查、可版本化、可建立 CI，並可做安全限制。

---

# 第六章　Schema 與資料契約

## 6.1 JSON Schema

JSON 應使用 Schema 驗證：

- 必填欄位；
- 型別；
- Enum；
- ID 格式；
- 數值上下限；
- 巢狀結構；
- 額外欄位限制。

## 6.2 CSV Schema

CSV 也需要正式 Schema，而不是只靠欄位名稱。

```yaml
table: characters
version: 0.1.0

columns:
  character_id:
    type: string
    required: true
    pattern: "^npc_[a-z0-9_]+$"

  level:
    type: integer
    min: 1
    max: 100

  unique:
    type: boolean

  persistence:
    type: enum
    values:
      - persistent
      - delta
      - regenerable
```

## 6.3 驗證層級

### L1：語法驗證

- JSON 是否合法；
- CSV 是否可解析；
- 編碼是否正確；
- 標題是否重複。

### L2：Schema 驗證

- 欄位；
- 型別；
- 枚舉；
- 範圍；
- 格式。

### L3：引用驗證

- 房間是否存在；
- NPC 所屬勢力是否存在；
- 任務物品是否存在；
- 出口目的地是否存在。

### L4：語義驗證

- 世界公理衝突；
- 任務不可完成；
- 地圖不可達；
- 經濟無限循環；
- 規則相互覆蓋。

### L5：目標能力驗證

- Evennia 是否支援；
- FluffOS 是否需要特殊編譯；
- Rust Runtime 是否有對應型別；
- 目標引擎是否缺少某語義。

---

# 第七章　唯一真實來源

## 7.1 不可多重真實來源

最危險的狀態是同一個角色同時存在於：

- `characters.csv`
- `characters.json`
- PostgreSQL
- Evennia Object
- AI 記憶
- EML 檔案

且每個地方都能被修改。

這會產生：

$$
D_{\mathrm{conflict}}
=
\sum_{i \neq j}
\operatorname{Diff}(D_i,D_j)
$$

## 7.2 建議責任分配

```text
CSV：大量平面定義資料
JSON：結構化世界與規則資料
Manifest：來源索引與編譯入口
EML：高密度語義與規則前端
World IR：正規化後的唯一編譯契約
Database：執行時狀態
Runtime Object：當前記憶體狀態
```

## 7.3 Source of Truth 規則

### 設計期

Authoring Layer 是真實來源。

### 編譯期

Validated World IR 是真實來源。

### 執行期

Runtime Database 是當前狀態來源。

### 更新期

世界定義修改回到 Authoring Layer，不直接逆寫來源資料，除非有明確 Export／Round-trip 工具。

---

# 第八章　定義資料與執行狀態分離

## 8.1 世界原型

```csv
character_id,name,default_location,base_level
npc_guard_001,沉默守衛,room_south_gate,3
```

這是角色定義。

## 8.2 執行時狀態

```json
{
  "instance_id": "npc_guard_001@world_instance_42",
  "current_location": "room_market",
  "current_health": 72,
  "quest_flags": [
    "warned_player"
  ],
  "alive": true
}
```

這是世界實例狀態。

## 8.3 不能混為一談

$$
E_{\mathrm{prototype}}
\neq
E_{\mathrm{instance}}
$$

原型可被重新編譯；實例記錄歷史。

若修改 NPC 基礎等級，不能自動假設所有已存在 NPC 都要同步變更。

因此需要遷移政策：

```text
Apply to new instances only
Apply to all instances
Apply only when not player-modified
Require migration script
```

---

# 第九章　ID、Namespace 與引用

## 9.1 所有實體必須有穩定 ID

禁止只以顯示名稱作為引用。

錯誤：

```text
北門守衛
```

正確：

```text
npc_gray_crown_gate_guard_001
```

名稱可以改，ID 不應隨意改。

## 9.2 Namespace

大型世界應支援命名空間：

```text
bt:npc:guard:001
bt:item:key:old_vault
core:skill:sword_basic
mod_weather:event:black_rain
```

形式上：

$$
\mathrm{ID}
=
N
:
T
:
K
$$

其中：

- $N$：Namespace；
- $T$：Entity Type；
- $K$：Local Key。

## 9.3 引用解析

編譯器需建立：

```text
Symbol Table
Reference Graph
Dependency Graph
Reverse Reference Index
```

以便回答：

- 刪除某物品會影響哪些任務？
- 改名某房間會影響哪些出口？
- 修改某規則會影響哪些技能？
- 某 NPC 是否仍被引用？

---

# 第十章　AI 維護流程

## 10.1 AI 不直接修改 Runtime

AI 應優先修改 Authoring Layer：

```text
User Request
→ AI Patch Proposal
→ JSON／CSV Diff
→ Validation
→ Human Review
→ Compile
→ Staging
→ Runtime
```

## 10.2 AI 批次操作

CSV 特別適合：

- 批次生成 500 個普通 NPC；
- 調整所有低階技能傷害；
- 為物品增加翻譯；
- 檢查重複名稱；
- 更新經濟價格；
- 生成測試資料。

JSON 適合：

- 生成任務；
- 新增勢力；
- 建立世界公理；
- 建立複雜事件；
- 建立規則集合。

## 10.3 AI 修改必須輸出 Diff

```yaml
patch_id: patch_0017
source_files:
  - data/items.csv
  - quests/main_quests.json

operations:
  - modify:
      file: data/items.csv
      row_id: item_old_vault_key
      field: rarity
      from: rare
      to: uncommon

  - modify:
      file: quests/main_quests.json
      path: /quests/0/rewards/0/count
      from: 1
      to: 2

validation:
  required:
    - schema
    - reference
    - quest_dependency
```

---

# 第十一章　版本與遷移

## 11.1 版本至少分為

```text
Authoring Schema Version
World Content Version
World IR Version
Compiler Version
Runtime Adapter Version
Save Version
```

## 11.2 Authoring Layer 遷移

例如：

```text
characters.csv v0.1
→ characters.csv v0.2
```

若新增欄位 `memory_policy`，應提供：

- 預設值；
- 遷移工具；
- 舊格式讀取；
- 警告；
- 移除期限。

## 11.3 編譯可重現性

同一來源、同一編譯器與同一設定應產生相同結果：

$$
C(A,v,s)
=
W
$$

應利用：

- 檔案雜湊；
- 編譯器版本；
- 固定排序；
- 固定隨機種子；
- Build Manifest；
- Content Digest。

---

# 第十二章　建議目錄

```text
worlds/
└── black-tide/
    ├── manifest.json
    ├── world.json
    │
    ├── axioms/
    │   └── core.json
    │
    ├── data/
    │   ├── characters.csv
    │   ├── items.csv
    │   ├── skills.csv
    │   ├── factions.csv
    │   └── recipes.csv
    │
    ├── maps/
    │   ├── regions.json
    │   ├── rooms.csv
    │   └── exits.csv
    │
    ├── quests/
    │   ├── main_quests.json
    │   └── side_quests.json
    │
    ├── rules/
    │   ├── combat.json
    │   ├── economy.json
    │   └── magic.json
    │
    ├── events/
    │   └── world_events.json
    │
    ├── localization/
    │   ├── zh-TW.csv
    │   └── en-US.csv
    │
    ├── schemas/
    │   ├── world.schema.json
    │   ├── characters.schema.yaml
    │   └── rooms.schema.yaml
    │
    ├── patches/
    ├── migrations/
    ├── tests/
    └── build/
```

`build/` 應視為可刪除的編譯產物，不應成為人工編輯來源。

---

# 第十三章　與 EML 的關係

## 13.1 JSON／CSV 不會被 EML 淘汰

EML 適合：

- 表達語義；
- 壓縮規則；
- 表達條件；
- 表達生命週期；
- 表達 Patch；
- 表達依賴；
- 作為 AI 與編譯器接口。

JSON／CSV 適合：

- 大量資料；
- 工具相容；
- 試算表；
- Git；
- 現有生態；
- 初期快速落地。

因此成熟架構為：

$$
\mathrm{JSON/CSV}
\cup
\mathrm{EML}
\rightarrow
W_{\mathrm{IR}}
$$

而非：

$$
\mathrm{EML}
\rightarrow
\text{淘汰 JSON／CSV}
$$

## 13.2 EML 可以成為語義覆蓋層

```eml
bind table "data/characters.csv" as characters

for character in characters {
    require character.level >= 1
    tag character.unique ? persistent : regenerable
}
```

EML 不必重複保存所有角色資料，而可以對 CSV 施加高層語義。

---

# 第十四章　第一版開發路線

## Phase 0：格式固定

- 定義 `manifest.json`；
- 定義 ID；
- 定義 Namespace；
- 定義 JSON／CSV 分工；
- 定義最小 Schema。

## Phase 1：載入與正規化

- JSON Loader；
- CSV Loader；
- 編碼；
- 型別轉換；
- 引用解析；
- 錯誤報告。

## Phase 2：World IR

- 統一實體；
- 關係圖；
- 規則；
- 任務；
- 地圖；
- Provenance。

## Phase 3：驗證

- Schema；
- 引用；
- 可達性；
- 任務依賴；
- 規則衝突。

## Phase 4：Evennia Adapter

- 房間；
- 出口；
- NPC；
- 物品；
- 任務；
- 世界版本。

## Phase 5：AI 編輯器

- AI 生成 JSON；
- AI 生成 CSV；
- Diff；
- Patch；
- Review；
- Rollback。

## Phase 6：EML 語義層

- 規則；
- 生命週期；
- 持久性；
- 條件；
- 多引擎編譯。

---

# 第十五章　反模式

## 15.1 所有資料都放在單一 JSON

結果：

- 檔案過大；
- Git 衝突；
- 難以多人協作；
- AI 修改範圍過大；
- 局部驗證困難。

## 15.2 所有資料都放在 CSV

結果：

- 巢狀資料被壓成字串；
- 任務與規則難以閱讀；
- 關係結構失真；
- 條件變得脆弱。

## 15.3 資料庫是唯一編輯來源

結果：

- Git 無法正常追蹤；
- 人工審查困難；
- AI 修改不可讀；
- 專案難以重建；
- 測試環境難以複製。

## 15.4 Runtime 反向覆蓋來源資料

若遊戲執行時直接寫回 `characters.csv` 或 `world.json`，會使：

- 原型與實例混合；
- 玩家行為污染設計資料；
- Git 出現大量無意義變更；
- 世界無法重編譯。

## 15.5 沒有 Manifest

讓編譯器猜測檔案會導致：

- 載入順序不確定；
- 不同環境結果不同；
- 隱藏依賴；
- 難以重現。

---

# 第十六章　理論意義

## 16.1 世界資料不是單一格式

世界本身具有多種尺度與資料形態。

因此：

$$
W
\neq
\text{Single File}
$$

而是：

$$
W
=
\bigcup_i D_i
+
\bigcup_j R_j
+
\bigcup_k P_k
$$

其中：

- $D_i$：資料集合；
- $R_j$：關係與規則；
- $P_k$：來源、版本與持久性資訊。

## 16.2 JSON／CSV 是人類—AI 協作介面

對人類而言，它們：

- 可讀；
- 可編；
- 可搜尋；
- 可 Diff；
- 可用試算表。

對 AI 而言，它們：

- 結構明確；
- 容易批次生成；
- 容易驗證；
- 容易建立 Patch；
- 容易限制輸出範圍。

因此 Authoring Layer 是人類與 AI 的共同工作表面。

## 16.3 CompilableWorld 不是取代來源，而是吸收來源

CompilableWorld 的成熟，不應以刪除 JSON／CSV 為標誌。

真正成熟的狀態是：

> 無論來源是 JSON、CSV、EML、小說或既有 MudLib，都能被正規化為同一個可驗證世界中間表示。

---

# 第十七章　結論

實作證明，在 CompilableWorld 尚未完成前，JSON 與 CSV 是必要工具；而在 CompilableWorld 完成後，它們仍有充分理由保留。

正確架構不是：

```text
JSON／CSV
→ 暫時使用
→ 未來刪除
```

而是：

```text
JSON／CSV／EML
→ Authoring Layer
→ Normalize
→ Validate
→ World IR
→ CompilableWorld
→ Runtime
```

其中：

- JSON 負責結構與巢狀語義；
- CSV 負責大量同型資料與批次維護；
- Manifest 負責來源索引、版本與編譯入口；
- Schema 負責型別與結構契約；
- World IR 負責跨格式正規化；
- CompilableWorld 負責驗證後的世界編譯；
- Database 負責執行時狀態；
- Runtime 負責實際遊戲運作。

最重要的原則是：

> 人類與 AI 編輯來源資料；編譯器建立世界；Runtime 執行世界；資料庫保存世界實例的歷史。

只要這四者邊界清楚，CompilableWorld 才能同時保持：

- 可讀；
- 可維護；
- 可驗證；
- 可遷移；
- 可版本化；
- 可跨引擎；
- 可由 AI 持續擴張。

---

# 附錄 A　最小 Manifest 範例

```json
{
  "world_id": "demo_world",
  "world_version": "0.1.0",
  "schema_version": "0.1.0",
  "namespace": "demo",
  "compiler_version": "0.1.0",
  "targets": [
    "evennia"
  ],
  "sources": {
    "world": "world.json",
    "characters": [
      "data/characters.csv"
    ],
    "items": [
      "data/items.csv"
    ],
    "rooms": [
      "maps/rooms.csv"
    ],
    "exits": [
      "maps/exits.csv"
    ],
    "quests": [
      "quests/quests.json"
    ]
  }
}
```

---

# 附錄 B　第一版驗證清單

- [ ] 所有 JSON 可解析
- [ ] 所有 CSV 使用 UTF-8
- [ ] 所有表格欄位符合 Schema
- [ ] 所有實體 ID 唯一
- [ ] 所有引用可解析
- [ ] 所有房間可達性已檢查
- [ ] 所有任務前置條件可滿足
- [ ] 所有世界公理無直接衝突
- [ ] Manifest 中檔案均存在
- [ ] 編譯器版本已記錄
- [ ] World IR 可重建
- [ ] Build 產物未被視為人工來源
- [ ] Runtime 狀態未回寫來源資料
- [ ] AI 修改以 Diff／Patch 呈現
- [ ] 版本遷移已有測試

---

# 附錄 C　建議的來源優先級

當同一資訊在多個來源出現時：

```text
人工核准 Patch
> 明確 EML 規則
> JSON 結構定義
> CSV 原型資料
> AI 推導值
> 預設值
```

若出現衝突，編譯器不應靜默選擇，而應輸出衝突報告。
