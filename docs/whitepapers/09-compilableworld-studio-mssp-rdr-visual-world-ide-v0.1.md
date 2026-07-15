# CompilableWorld Studio：基於 MSSP × RDR 的可視化世界狀態編譯與驗證工作台

**文件版本：** v0.1  
**文件性質：** 架構轉向規格書／產品設計文件／MVP 實作計畫  
**核心方法論：** MSSP × RDR  
**目標系統：** CompilableWorld Runtime、MUD 世界、模擬世界、Agent 可操作世界  
**主要定位：** 世界定義、狀態編輯、規則編譯、靜態驗證、動態模擬與因果觀測的統一工作台

---

# 摘要

CompilableWorld 原先容易沿著一般引擎開發路徑前進：

$$
\text{Python Runtime}
\rightarrow
\text{逐步增加世界邏輯}
\rightarrow
\text{最後補上一個 GUI}
$$

此路徑雖然可以持續增加功能，卻會造成三個結構性問題：

1. 世界設計被分散在 Python 類別、函數、設定檔與測試之中；
2. 人類只能透過程式碼間接理解世界，Agent 也必須反覆重讀整個專案；
3. 狀態、函數、事件、關係、任務與模組的錯誤，往往要等到執行後才暴露。

本文件提出正式的架構反轉：

$$
\boxed{
\text{CompilableWorld Studio}
\rightarrow
\text{Validated World IR}
\rightarrow
\text{Runtime Targets}
}
$$

世界的本體不再是某一份 Python 程式，而是由可視化介面、文字 DSL、結構化資料與狀態圖共同投影的統一世界中介表示。

Python Runtime 退回其正確位置：

> 它是第一個參考執行器，而不是世界本身。

CompilableWorld Studio 將成為：

- 世界本體編輯器；
- 實體與狀態 Schema 編輯器；
- 函數與公式註冊中心；
- 事件、觸發器與狀態機設計器；
- 模組依賴與權限治理器；
- 靜態驗證器；
- 動態模擬器；
- 因果 Trace 觀測器；
- 人類與 Agent 共用的世界 IDE。

---

# 一、架構轉向

## 1.1 舊模型：程式碼先行

舊模型可表示為：

```text
需求
  ↓
手寫 Python
  ↓
增加類別與函數
  ↓
執行測試
  ↓
發現狀態錯誤
  ↓
回頭修改程式
```

其世界知識分散於：

- Python 類別；
- 建構函數；
- 字典與常數；
- JSON／YAML；
- 事件處理器；
- 任務腳本；
- 測試；
- 文件；
- 人類記憶。

此時世界的真相來源並不唯一。

$$
\text{World Truth}
=
\text{Code}
\cup
\text{Config}
\cup
\text{Docs}
\cup
\text{Implicit Assumptions}
$$

這使得：

- 文件與實作容易漂移；
- 狀態轉移難以整體觀看；
- 模組依賴難以移除；
- Agent 很難只修改局部；
- 同一世界難以編譯到不同 Runtime。

---

## 1.2 新模型：世界定義先行

新模型為：

```text
世界設計
  ↓
CompilableWorld Studio
  ↓
World IR
  ↓
靜態驗證
  ↓
模擬與測試
  ↓
編譯至 Python／Rust／JavaScript
  ↓
Runtime Trace 回流 Studio
```

形式化表示：

$$
W
=
(
M,
E,
S,
F,
V,
X,
T,
P,
Q
)
$$

其中：

- $M$：模組集合；
- $E$：實體與實體類型；
- $S$：狀態與狀態空間；
- $F$：函數與公式；
- $V$：事件；
- $X$：觸發器與動作；
- $T$：狀態轉移；
- $P$：權限與政策；
- $Q$：測試情境與契約。

世界首先是一個可驗證的結構，再被編譯成可執行系統。

---

## 1.3 核心產品判斷

CompilableWorld Studio 不是：

- Runtime 的附加管理介面；
- Python 程式碼生成器的外殼；
- 另一個普通節點編輯器；
- 只用來做 MUD 地圖的工具；
- 只讓不會寫程式的人使用的低階介面。

它應被定位為：

> 世界狀態、規則、函數、模組、因果與執行軌跡的主要設計環境。

其核心公式為：

$$
\boxed{
\text{World Definition}
>
\text{Runtime Implementation}
}
$$

符號 $>$ 在此表示架構層級，而不是數值大小。

---

# 二、來自 MOD 編輯器的正確啟發

成熟遊戲的 MOD 編輯器往往已經包含：

- 角色；
- 人物設定；
- 角色特性；
- 物品；
- 環境物；
- 地圖實體；
- 實體互動；
- 地區；
- 地圖；
- 觸發器；
- 公式；
- 任務；
- 隨機任務；
- 陣營；
- 技能或武學；
- 知識；
- 狀態效果；
- 配方；
- 商店；
- 動畫；
- 音效；
- 戰鬥陣型；
- 地面效果。

這些分類實際上已經形成一套遊戲世界本體：

$$
\mathcal{O}_{world}
=
\{
\text{Entity},
\text{State},
\text{Rule},
\text{Event},
\text{Relation},
\text{Space},
\text{Time},
\text{Asset}
\}
$$

問題不在於這類編輯器能力不足，而在於它們常被定位為：

> 遊戲完成後提供給玩家的附屬 MOD 工具。

CompilableWorld 應倒轉此層級：

> 可視化世界編輯器不是 Runtime 的附屬物，而是 Runtime 的上游真相來源。

---

# 三、設計原則：不是單一節點圖，而是多重同步投影

純節點式編輯器會迅速產生視覺義大利麵：

$$
\text{Visual Programming}
\rightarrow
\text{Visual Spaghetti}
$$

因此 Studio 不應將所有東西強迫放進同一張無限畫布。

正確設計是：

$$
\boxed{
\text{Form View}
\leftrightarrow
\text{Table View}
\leftrightarrow
\text{Graph View}
\leftrightarrow
\text{State Machine View}
\leftrightarrow
\text{DSL View}
}
$$

所有視圖皆是同一份 AST／IR 的投影，而不是彼此獨立的資料。

---

## 3.1 表單視圖

適合：

- 單一實體；
- 單一函數；
- 單一事件；
- 欄位與預設值；
- 角色設定；
- 任務基本資料。

示例：

```yaml
entity:
  id: npc.innkeeper
  type: character
  name: 馬洛
  location: room.inn.main
  traits:
    - cautious
    - pragmatic
```

---

## 3.2 表格視圖

適合：

- 大量物品；
- 大量角色；
- 狀態效果；
- 函數註冊；
- 關係規則；
- 批次修改。

例如：

| ID | 類型 | 名稱 | 模組 | 狀態 |
|---|---|---|---|---|
| `npc.innkeeper` | Character | 馬洛 | `core.village` | 正常 |
| `item.old_map` | Item | 破舊地圖 | `quest.caravan` | 正常 |
| `effect.poison` | Effect | 中毒 | `combat.status` | 警告 |

---

## 3.3 狀態機視圖

適合：

- 任務；
- 關係；
- AI 行為；
- 戰鬥階段；
- 建築狀態；
- 世界事件；
- 生命周期。

示例：

```text
[locked]
    │ reputation >= 2
    ▼
[offered]
    │ player.accept
    ▼
[active]
    ├── caravan.found ─────► [completed]
    ├── survivor.died ─────► [failed]
    └── timeout 7 days ────► [expired]
```

---

## 3.4 依賴圖視圖

適合：

- 模組依賴；
- 函數呼叫；
- 事件影響；
- 資源流；
- 因果鏈；
- 循環檢查；
- RDR L4 排程。

---

## 3.5 DSL／原始資料視圖

適合 Agent 與進階開發者：

```text
quest missing_caravan {
    initial locked

    locked -> offered
        on npc.offer_quest
        when player.reputation.village >= 2

    offered -> active
        on player.accept_quest

    active -> completed
        on caravan.found

    active -> failed
        on survivor.died

    active -> expired
        after 7d
}
```

所有視圖修改後必須立即同步。

---

# 四、MSSP × RDR 在 Studio 中的具體映射

MSSP 與 RDR 不再只是文件方法論，而將成為 Studio 的結構骨架。

---

## 4.1 雙平面

| 平面 | 方法論 | Studio 對應 |
|---|---|---|
| 描述／認知平面 | MSSP | 專案、模組、本體、視圖、索引、敘事 |
| 執行／運行平面 | RDR | 函數、派發、圖排程、快取、監控、閘門 |

兩者交界為：

$$
\text{FMS INDEX}
\leftrightarrow
\text{RDR Registry}
$$

人類可讀的能力宣告，必須同時是機器可執行的函數註冊來源。

---

## 4.2 FMS：世界工程總覽

FMS 在 Studio 中對應世界專案首頁。

```yaml
world:
  id: jianghu_world
  name: 江湖世界
  version: 0.1.0

narrative:
  purpose: >
    建立可由人類與 Agent 共同修改、
    驗證與持續運行的武俠世界。

observer_classes:
  - human_designer
  - ai_agent
  - runtime_operator

runtime_targets:
  - python
  - javascript_simulator

core_modules:
  - entity.core
  - state.core
  - event.core
  - dispatch.rdr
  - snapshot.core

feature_modules:
  - quest
  - relationship
  - faction
  - economy
  - weather
```

FMS 必須維持純元資料，不包含可執行控制器程式。

---

## 4.3 SMS：穩定核心模組

SMS 對應不可輕易移除的核心能力：

- Entity Core；
- State Core；
- Event Core；
- Function Registry；
- RDR Dispatch；
- Snapshot；
- Diagnostics；
- Permission Core。

Studio 應標記高扇入核心模組，並顯示其影響範圍。

---

## 4.4 TMS：可替換功能模組

TMS 對應：

- 任務；
- 關係；
- 戰鬥；
- 門派；
- 天氣；
- 經濟；
- 家園；
- 對話；
- Agent 自治。

每個 TMS 必須支援：

$$
\operatorname{Disable}(M_i)
\rightarrow
\operatorname{Validate}(W-M_i)
$$

若移除某模組後仍有引用，Studio 應立即列出：

- 缺失函數；
- 缺失狀態；
- 缺失事件；
- 缺失 Schema；
- 不可達任務；
- 無效 UI。

---

## 4.5 DMS：診斷與可觀測性

DMS 對應：

- 呼叫 Trace；
- 契約驗證；
- 狀態轉換記錄；
- 事件因果鏈；
- 快取命中；
- RDR 派發統計；
- 循環；
- 動態窄帶；
- 失效與降級。

DMS 規定「觀察什麼」，RDR L3 與 L5 提供「在哪裡觀察」。

---

# 五、RDR 五層在 Studio 中的實體化

## 5.1 L1：函數定義層

L1 必須是：

- 引用透明；
- 無隱藏狀態；
- 無未聲明 I/O；
- 輸入輸出具型別；
- 可被測試；
- 可被快取。

函數定義示例：

```yaml
function:
  id: relation.add_trust
  version: 1.0.0
  category: relationship
  purity: pure

inputs:
  current:
    type: float
  delta:
    type: float
  minimum:
    type: float
    default: 0.0
  maximum:
    type: float
    default: 1.0

output:
  type: float

expression:
  clamp(current + delta, minimum, maximum)
```

---

## 5.2 L2：宣告式呼叫層

L2 不直接 import 函數，只宣告能力名稱：

```yaml
actions:
  - call: relation.add_trust
    args:
      current: target.relation.trust
      delta: 0.20
```

其核心原則：

$$
\text{Call Intent}
\neq
\text{Implementation Binding}
$$

---

## 5.3 L3：具現化派發層

Studio 必須提供 Registry 面板：

| 名稱 | 版本 | 純度 | 實作 | 使用次數 | 狀態 |
|---|---|---|---|---:|---|
| `relation.add_trust` | 1.0.0 | Pure | Python | 128 | 正常 |
| `quest.transition` | 0.4.0 | Stateful | Runtime | 37 | 正常 |
| `economy.price` | — | Pure | 缺失 | 9 | 錯誤 |

所有函數呼叫皆經過 RDR L3：

$$
\operatorname{dispatch}
(
\text{name},
\text{args},
\text{context}
)
$$

L3 可集中掛載：

- Memoization；
- 去重；
- 權限檢查；
- Trace；
- 契約；
- 版本解析；
- Adapter；
- 執行目標選擇。

---

## 5.4 L4：圖排程層

Studio 必須區分三種依賴：

### 無環 DAG

使用拓撲序求值。

### 時間迴路

例如：

$$
A_{t+1}=f(B_t)
$$

此類循環合法，因為跨越時間步。

### 同步代數環

例如：

$$
A_t=f(B_t)
$$

$$
B_t=g(A_t)
$$

此類環必須：

- 定義固定點語義；
- 定義最大迭代；
- 定義收斂條件；
- 或拒絕編譯。

對圖 $G=(V,E)$，L4 必須進行 SCC 分解：

$$
G
\rightarrow
\operatorname{SCC}(G)
\rightarrow
G_{\text{condensed}}
$$

每個 SCC 必須被標記為：

- 錯誤循環；
- 時間循環；
- 固定點循環；
- 允許的遞迴群；
- 未決定。

---

## 5.5 L5：元控制與適用域閘門

L5 在 Studio 中對應：

- 快取是否啟用；
- 模組是否載入；
- 函數是否物化；
- 重算策略；
- 耦合強度；
- 閘門；
- 降級；
- Runtime 策略。

它必須顯示：

- 重用率；
- 扇入；
- 快取命中；
- SCC 數量；
- 振盪；
- 異質 spread；
- 派發成本；
- 是否值得使用 RDR。

當負載不適合時，L5 應可回報：

```text
RDR Gate: SKIP
Reason:
- reuse ratio: 0.04
- average function cost: 0.8 μs
- dispatch overhead exceeds projected benefit
```

---

# 六、核心 World IR

Studio v0.1 應建立以下核心 IR。

---

## 6.1 ModuleIR

```yaml
module:
  id: relationship.core
  version: 0.1.0
  kind: feature
  dependencies:
    - entity.core
    - state.core
    - event.core
  exports:
    - relation.add_trust
    - relation.changed
  optional: true
```

---

## 6.2 EntityIR

```yaml
entity_type:
  id: character
  fields:
    name:
      type: string
      required: true
    age:
      type: integer
      minimum: 0
    location:
      type: ref<room>
    traits:
      type: list<ref<trait>>
```

---

## 6.3 StateIR

```yaml
state:
  id: relation.trust
  owner: relation
  type: float
  range: [0.0, 1.0]
  default: 0.0
  persistence: snapshot
  visibility:
    human: summary
    agent: exact
```

---

## 6.4 FunctionIR

```yaml
function:
  id: math.clamp
  purity: pure
  inputs:
    value: float
    minimum: float
    maximum: float
  output: float
  expression:
    op: min
    args:
      - ref: maximum
      - op: max
        args:
          - ref: minimum
          - ref: value
```

---

## 6.5 EventIR

```yaml
event:
  id: npc.saved_by
  payload:
    npc: ref<character>
    rescuer: ref<character>
    context: ref<event_context>
```

---

## 6.6 TriggerIR

```yaml
trigger:
  id: relationship.on_saved
  on: npc.saved_by
  priority: 100
  cooldown: none
  guards:
    - call: character.is_alive
      args:
        target: event.npc
  actions:
    - call: relation.add_trust
      args:
        source: event.npc
        target: event.rescuer
        delta: 0.20
```

---

## 6.7 TransitionIR

```yaml
transition:
  id: quest.caravan.active_to_completed
  machine: quest.caravan
  from: active
  to: completed
  on: caravan.found
  guards:
    - quest.caravan.survivor_alive == true
```

---

## 6.8 PermissionIR

```yaml
permission:
  actor: agent.sect_manager
  allow:
    - sect.assign_low_risk_work
    - sect.schedule_rest
    - sect.generate_report
  deny:
    - sect.declare_war
    - sect.expel_core_member
```

---

## 6.9 ScenarioIR

```yaml
scenario:
  id: relationship.life_saving_test
  given:
    npc_a.relation.trust.npc_b: 0.20
    npc_a.relation.intimacy.npc_b: 0.00
  when:
    emit:
      event: npc.saved_by
      npc: npc_a
      rescuer: npc_b
  expect:
    npc_a.relation.trust.npc_b: 0.40
    npc_a.relation.intimacy.npc_b: 0.00
```

---

## 6.10 執行期 IR

執行後產物包括：

- `TraceIR`
- `SnapshotIR`
- `DiagnosticIR`
- `MetricIR`
- `DecisionIR`

完整閉環：

$$
\begin{aligned}
&\text{ModuleIR}
+\text{EntityIR}
+\text{StateIR}
+\text{FunctionIR}\\
&+\text{EventIR}
+\text{TriggerIR}
+\text{TransitionIR}
+\text{PermissionIR}\\
&\longrightarrow
\text{Validated World IR}\\
&\longrightarrow
\text{Runtime}\\
&\longrightarrow
\text{TraceIR}
+\text{SnapshotIR}
+\text{DiagnosticIR}
\end{aligned}
$$

---

# 七、Studio 主要工作區

## 7.1 世界總覽

顯示：

- 世界名稱與版本；
- FMS NARRATIVE；
- SMS／TMS；
- Runtime Targets；
- 觀察者類；
- 編譯狀態；
- 警告；
- 最近模擬；
- Agent 修改。

---

## 7.2 本體與類型註冊表

管理：

- 實體類型；
- 狀態類型；
- 關係類型；
- 事件類型；
- 枚舉；
- 單位；
- 時間尺度；
- 引用規則。

---

## 7.3 實體編輯器

功能：

- 建立實體；
- 批次建立；
- 複製模板；
- Schema 驗證；
- 引用搜尋；
- 反向引用；
- 模組歸屬；
- 可見性；
- 權限。

---

## 7.4 函數與公式工作室

功能：

- 函數表單；
- 公式 AST；
- 節點圖；
- DSL；
- 型別推導；
- 純度檢查；
- 單元測試；
- 函數版本；
- Registry；
- 使用位置。

---

## 7.5 事件與觸發器工作室

一個 Trigger 應被拆為：

$$
\text{Event}
+
\text{Guard}
+
\text{Action}
+
\text{Priority}
+
\text{Timing}
+
\text{Scope}
$$

介面需支援：

- 一次性；
- 重複；
- 冷卻；
- 延時；
- 排程；
- 事件聚合；
- 防止重入；
- 防止無限觸發。

---

## 7.6 狀態機工作室

支援：

- 初始狀態；
- 終止狀態；
- 守衛；
- 轉移事件；
- 超時；
- 並行區域；
- 子狀態機；
- 歷史狀態；
- 進入／退出動作；
- 不可達狀態分析。

---

## 7.7 依賴與因果圖

圖層可切換：

- 模組依賴；
- 函數呼叫；
- 狀態讀寫；
- 事件發射；
- 任務依賴；
- 權限關係；
- Runtime Trace。

圖不只是視覺展示，必須可執行分析：

- SCC；
- 拓撲排序；
- 扇入；
- 扇出；
- 高耦合區；
- 孤立節點；
- 循環；
- 移除影響。

---

## 7.8 模擬器

功能：

- 單步；
- 連續運行；
- 暫停；
- 重播；
- 時間倍率；
- 注入事件；
- 修改狀態；
- 分支模擬；
- 快照；
- 比較兩條時間線；
- 隨機種子固定；
- Agent 行動回放。

---

## 7.9 Runtime Observatory

顯示具體因果鏈：

```text
Time: Day 17, 14:20
Event: npc.saved_by

State changes:
trust       0.21 → 0.41
obligation  0.00 → 0.50
gratitude   0.00 → 0.70
intimacy    0.04 → 0.04

Guards:
✓ entity is adult
✓ no kinship conflict
✗ reciprocity insufficient

Transition:
acquaintance → friend
Result: rejected

Reason:
positive interaction history < required threshold
```

這使動態系統符合 MSSP × RDR 的第二判據：

> 系統動力學必須可以在運行中被即時認出其 régime。

---

# 八、靜態驗證器

編譯前至少檢查以下類型。

---

## 8.1 Schema 驗證

- 必填欄位；
- 型別；
- 範圍；
- 枚舉；
- 引用類型；
- 預設值；
- 不變量。

---

## 8.2 引用完整性

- 缺失 Entity；
- 缺失 Function；
- 缺失 Event；
- 缺失 State；
- 缺失 Module；
- 缺失 Asset；
- 版本不相容。

---

## 8.3 狀態機驗證

- 無初始狀態；
- 多重初始狀態；
- 不可達狀態；
- 無出口死狀態；
- 非預期循環；
- 永不成立守衛；
- 衝突轉移；
- 未處理事件。

---

## 8.4 函數驗證

- 型別錯誤；
- 純函數中存在副作用；
- 未聲明 I/O；
- 非決定性函數被錯誤快取；
- 無終止遞迴；
- 未定義運算；
- 除以零；
- 單位錯配。

---

## 8.5 事件驗證

- 無限觸發鏈；
- 事件自我重入；
- 優先級衝突；
- 未界定的重複事件；
- 冷卻失效；
- 跨模組循環依賴。

---

## 8.6 權限驗證

- Agent 擁有未授權 Action；
- 高風險 Action 無人工批准；
- 模組讀寫超出作用域；
- 私有狀態被公開；
- 只讀狀態被修改。

---

## 8.7 MSSP 同步驗證

- FMS INDEX 與 Registry 不一致；
- SMS 被錯誤設為可移除；
- TMS 被硬編碼引用；
- 程式碼存在但 FMS 未宣告；
- FMS 宣告但無實作。

---

# 九、動態驗證與情境測試

靜態正確不等於動態合理。

Studio 必須支援情境測試：

$$
\text{Given}
\rightarrow
\text{When}
\rightarrow
\text{Then}
$$

以及性質測試：

$$
\forall x\in D,\quad P(x)
$$

例如關係系統：

$$
\Delta intimacy=0
$$

若事件僅代表救命之恩，而沒有親密互動。

門派系統：

$$
health<0.7
\Rightarrow
\text{禁止自動高風險派遣}
$$

任務系統：

$$
state=\text{completed}
\Rightarrow
\neg\operatorname{transitionTo}(\text{active})
$$

---

# 十、人類與 Agent 的共同編輯模式

## 10.1 人類負責

- 世界目的；
- 模組邊界；
- 核心概念；
- 狀態語義；
- 重大關係；
- 權限；
- 驗收；
- 例外判斷。

---

## 10.2 Agent 負責

- 批次建立實體；
- 生成 Schema；
- 生成狀態機；
- 補齊重複規則；
- 產生函數骨架；
- 生成測試；
- 修正引用；
- 執行模擬；
- 分析 Trace；
- 提交 AST／IR Patch。

---

## 10.3 同一世界，不同視圖

Agent 看到：

```yaml
transition:
  id: relation.acquaintance_to_friend
  from: acquaintance
  to: friend
  guards:
    - trust >= 0.45
    - positive_interactions >= 5
    - interaction_days >= 30
```

人類看到：

```text
[普通相識]
     │
     │ 信任 ≥ 0.45
     │ 正向互動 ≥ 5
     │ 相識 ≥ 30 天
     ▼
[朋友]
```

兩者必須由同一 IR 產生。

---

## 10.4 Agent Diff Review

Agent 不應直接在世界中永久寫入。

工作流：

```text
Agent Request
  ↓
Generate IR Patch
  ↓
Schema Validation
  ↓
Semantic Validation
  ↓
Visual Diff
  ↓
Human Accept / Reject
  ↓
Commit
```

Diff 應顯示：

- 新增的實體；
- 刪除的狀態；
- 變更的函數；
- 轉移條件差異；
- 模組依賴變化；
- 模擬結果差異；
- 可能受影響的測試。

---

# 十一、與 EveGlyph 工作區的關係

CompilableWorld Studio 不應被硬塞成 Markdown 編輯器的一個頁籤。

較合理的關係是共享底層工作區能力：

```text
Shared Workspace Core
├─ Local workspace
├─ Git
├─ Agent bridge
├─ Diff review
├─ Permissions
├─ Version history
└─ Project navigation
       │
       ├─ EveGlyph Editor
       │    └─ Markdown／論文／文件
       │
       └─ CompilableWorld Studio
            └─ Entity／State／Rule／Graph／Simulation
```

兩者共享：

- 本地優先；
- Agent；
- Git；
- Diff；
- 權限；
- 檔案管理；
- 版本控制。

但前台編輯模型不同。

---

# 十二、多目標編譯

World IR 不應綁死 Python。

---

## 12.1 Python Runtime

定位：

- 參考實作；
- 快速驗證；
- 開發方便；
- 測試；
- 原型。

---

## 12.2 JavaScript Simulator

定位：

- 瀏覽器內模擬；
- Studio 即時預覽；
- 分享測試情境；
- 無需啟動完整後端。

---

## 12.3 Rust Runtime

定位：

- 大型世界；
- 高性能；
- 高併發；
- 長期 Runtime；
- 可嵌入伺服器。

---

## 12.4 編譯一致性

不同 Runtime 必須通過相同的 ScenarioIR。

$$
\operatorname{Run}_{Python}(Q)
=
\operatorname{Run}_{Rust}(Q)
=
\operatorname{Run}_{JS}(Q)
$$

此等式表示語義結果一致，不要求效能與內部執行順序完全相同。

---

# 十三、版本、遷移與持久化

## 13.1 穩定 ID

顯示名稱可變，ID 不應隨意變更。

```yaml
id: quest.missing_caravan
display_name: 失蹤的商隊
```

---

## 13.2 Schema 版本

```yaml
schema:
  id: character
  version: 2
```

任何破壞性變更必須有 Migration。

---

## 13.3 Snapshot

Snapshot 必須記錄：

- World IR 版本；
- Runtime 版本；
- 模組版本；
- 隨機種子；
- 時間；
- 實體狀態；
- Agent 狀態；
- 外部擴展狀態。

---

## 13.4 熱重載

可安全熱重載的項目：

- 純函數；
- 顯示文字；
- 部分公式；
- 新增任務；
- 新增實體模板。

需要遷移或重啟的項目：

- 刪除核心狀態；
- 修改 Entity Schema；
- 改變持久化類型；
- 修改模組 ID；
- 改變狀態機語義。

---

# 十四、CompilableWorld Studio v0.1 範圍

第一版不追求完整遊戲引擎。

只建立一個完整閉環：

$$
\text{定義}
\rightarrow
\text{驗證}
\rightarrow
\text{模擬}
\rightarrow
\text{編譯}
\rightarrow
\text{觀測}
$$

---

## 14.1 必須包含

### 專案與模組

- 建立世界；
- FMS；
- SMS／TMS；
- 模組啟用；
- 相依檢查。

### Entity 與 State

- Entity Type；
- 欄位；
- 型別；
- 實體；
- 狀態；
- 關係。

### Function

- 函數簽名；
- 純度；
- 公式；
- Registry；
- 單元測試。

### Event 與 Trigger

- Event；
- Guard；
- Action；
- Priority；
- Cooldown。

### State Machine

- 狀態；
- 轉移；
- 超時；
- 終止；
- 可達性檢查。

### Validator

- Schema；
- 引用；
- 型別；
- 循環；
- 不可達；
- 權限。

### Simulator

- 單步；
- Trace；
- Snapshot；
- 重播；
- Scenario。

### Compiler

- `world.ir.json`
- Python Runtime；
- Python 測試。

---

## 14.2 暫不包含

- 完整 3D 場景；
- 高階動畫編輯；
- 音效製作；
- 大型多人網路同步；
- 完整 MMO 後端；
- 自由程式碼執行節點；
- 自動發布；
- 無限制 Agent 自治；
- Rust 完整 Runtime。

---

# 十五、第一個垂直切片

建立一個最小武俠／MUD 世界：

```text
村莊廣場
  │
  └── 酒館
        ├── 酒館老闆
        ├── 求救信
        └── 地窖入口
```

世界包含：

- 2 個 Room；
- 1 名 Player；
- 1 名 NPC；
- 1 件物品；
- 1 個關係向量；
- 1 條任務；
- 1 個狀態效果；
- 5 個純函數；
- 3 個事件；
- 4 個 Trigger；
- 1 個任務狀態機；
- 1 個 Agent 權限集。

完整流程：

1. 在 Studio 建立實體與 Schema。
2. 建立關係狀態。
3. 建立函數。
4. 建立救命事件。
5. 建立關係守衛。
6. 建立任務狀態機。
7. 執行靜態驗證。
8. 執行情境模擬。
9. 編譯到 Python Runtime。
10. 執行並產生 Trace。
11. 將 Trace 回傳 Studio。
12. 視覺化因果鏈。
13. Agent 提交一個規則修改。
14. 人類在 Diff 中接受或拒絕。
15. 重新編譯並比較結果。

---

# 十六、MVP 驗收條件

v0.1 必須達成：

1. 同一項資料可在表單、圖與 DSL 中同步修改。
2. Agent 可只修改 World IR，不必重寫 Python。
3. 缺失引用可在編譯前發現。
4. 任務不可達狀態可被檢測。
5. 函數純度可被聲明與驗證。
6. 循環依賴可被 SCC 分析。
7. 一項世界事件可產生完整 Trace。
8. Snapshot 可保存並恢復。
9. Python Runtime 可由 IR 自動生成。
10. Scenario 測試可同時在模擬器與 Python Runtime 通過。
11. 關閉一個 TMS 後可重新驗證世界。
12. Agent Patch 必須通過 Diff Review 才能寫入。

可形式化為：

$$
\boxed{
V_{\text{multi-view}}
\land
V_{\text{schema}}
\land
V_{\text{graph}}
\land
V_{\text{runtime}}
\land
V_{\text{trace}}
\land
V_{\text{agent}}
}
$$

---

# 十七、建議技術目錄

```text
compilableworld-studio/
├─ apps/
│  ├─ studio-web/
│  └─ simulator/
├─ packages/
│  ├─ world-ir/
│  ├─ schema/
│  ├─ validator/
│  ├─ graph-analysis/
│  ├─ rdr-dispatch/
│  ├─ simulator-core/
│  ├─ compiler-python/
│  ├─ trace-ir/
│  └─ agent-bridge/
├─ runtimes/
│  └─ python/
├─ examples/
│  └─ village-inn/
├─ tests/
│  ├─ scenarios/
│  ├─ compiler/
│  ├─ validator/
│  └─ runtime-conformance/
├─ docs/
│  ├─ architecture/
│  ├─ ir/
│  ├─ mssp-rdr/
│  └─ decisions/
└─ workspace/
   ├─ projects/
   ├─ snapshots/
   └─ traces/
```

---

# 十八、實作階段

## 階段 0：架構凍結

- 定義核心 IR；
- 定義 ID 規則；
- 定義 Module 邊界；
- 定義純度與副作用；
- 定義 Trace；
- 定義 Scenario。

---

## 階段 1：Headless Core

先不做漂亮 GUI，完成：

- World IR；
- JSON Schema；
- Validator；
- Graph Analysis；
- Python Compiler；
- Scenario Runner。

此階段確保 Studio 不是沒有語義的前端殼。

---

## 階段 2：最小 Studio

建立：

- 專案總覽；
- Entity 表單；
- State 表格；
- Function 編輯；
- Trigger 編輯；
- State Machine；
- Diagnostics。

---

## 階段 3：模擬與觀測

建立：

- 單步執行；
- Timeline；
- Trace；
- Snapshot；
- 因果圖；
- 狀態 Diff。

---

## 階段 4：Agent 協作

建立：

- Agent API；
- IR Patch；
- Diff；
- 驗證；
- 權限；
- 人工批准；
- 回滾。

---

## 階段 5：Runtime 擴展

- JavaScript Simulator；
- Rust Runtime；
- 多世界；
- 多 Agent；
- 分散式 RDR；
- 集群監控。

---

# 十九、主要風險

## 19.1 GUI 先於語義

風險：

> 做出很好看的節點編輯器，但沒有穩定 IR 與驗證語義。

對策：

$$
\text{IR First}
\rightarrow
\text{Validator}
\rightarrow
\text{GUI}
$$

---

## 19.2 無限制節點化

風險：

- 圖過大；
- 難以閱讀；
- 難以 Diff；
- Agent 修改脆弱。

對策：

- 多視圖；
- 分層；
- 子圖；
- 模組；
- 表格；
- DSL；
- 摘要。

---

## 19.3 允許任意 Python

風險：

- 無法跨 Runtime；
- 無法驗證；
- 純度失效；
- Agent 可執行任意代碼。

對策：

- v0.1 使用受限 Expression AST；
- 副作用只能透過受控 Command；
- 任意代碼只能存在於外部 Adapter；
- Adapter 必須明確標記不透明。

---

## 19.4 World IR 過早膨脹

風險：

> 一開始就試圖包含所有遊戲類型。

對策：

先支援：

- MUD；
- 任務；
- 關係；
- 狀態效果；
- Agent 權限。

再逐步擴展。

---

## 19.5 Studio 與 Runtime 漂移

對策：

- 共享 Schema；
- Conformance Tests；
- Snapshot Version；
- Scenario；
- Registry 同步；
- CI。

---

# 二十、立即執行清單

1. 從現有 Runtime 提取最小 Entity／State／Event 結構。
2. 正式定義九個核心 IR。
3. 建立 `world.ir.schema.json`。
4. 建立 ID 與引用規則。
5. 實作 Headless Validator。
6. 實作 SCC 與拓撲分析。
7. 建立受限 Expression AST。
8. 建立第一個 Python Compiler。
9. 建立 `village-inn` 示例世界。
10. 建立 Scenario Runner。
11. 再建立 Studio 最小介面。
12. 將 Agent 修改限制為 IR Patch。
13. 接入 Git Diff。
14. 實作 TraceIR 與 Runtime Observatory。
15. 停止無結構地繼續堆疊 Python 世界邏輯。

---

# 二十一、結論

CompilableWorld 真正需要的，不是更多散落的 Python 函數，而是一個能夠讓大量世界函數、狀態、事件、模組與因果鏈共同被：

- 定義；
- 批次生成；
- 視覺理解；
- 靜態驗證；
- 動態模擬；
- 編譯執行；
- 即時觀測；
- Agent 修改；
- 人類審核。

的主力工作環境。

最終架構可總結為：

$$
\boxed{
\text{MSSP 描述世界}
+
\text{RDR 執行世界}
+
\text{Studio 連接兩者}
}
$$

而其產品核心是：

> 世界不是寫死在某一種程式語言中的應用程式；世界是一份可以被不同觀察者理解、被不同 Runtime 執行、被 Agent 修改、被驗證器證偽、並在運行中持續顯示其因果結構的可編譯定義。

這才是 `CompilableWorld` 應有的完整含義。
