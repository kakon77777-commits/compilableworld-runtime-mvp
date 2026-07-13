---
title: "超大型階層式有限狀態世界 MUD：AI 驅動的複合行為、事件轉導與可編譯世界狀態機"
subtitle: "從傳統文字指令到自然語言 Action IR、分層狀態機與事件溯源世界"
author: "Neo.K / EVEMISSLAB"
version: "v0.1"
status: "技術架構論文草案"
date: "2026-07-13"
language: "zh-TW"
keywords:
  - MUD
  - Finite State Machine
  - Hierarchical State Machine
  - Action IR
  - Event IR
  - CompilableWorld
  - AI Agent
  - Event Sourcing
  - World State Machine
  - Natural Language Interface
---

# 超大型階層式有限狀態世界 MUD：AI 驅動的複合行為、事件轉導與可編譯世界狀態機

## 摘要

本文提出一種超越傳統 MUD 指令模型的遊戲架構：以自然語言為玩家輸入介面，以 AI 作為意圖解析與行為編譯器，並以階層式、可組合、事件驅動的有限狀態世界作為真正執行核心。

傳統 MUD 主要依賴有限動詞與目標組合，例如 `look`、`get sword`、`kill goblin`。此模型雖然穩定，但難以表達多步驟、條件式、隱蔽式、協作式與具有時序要求的複雜行為。本文所提出的系統允許玩家使用自然語言描述更高複雜度的意圖，例如：

> 假裝沒有注意守衛，慢慢靠近門邊，等他轉身後，用左手取出藏在衣服裡的鑰匙，再嘗試無聲開門。

AI 不直接決定結果，而是將此自然語言轉換為受限、可驗證、可排程的 Action IR。確定性規則引擎再依據角色狀態、世界狀態、物品、時間、環境與衝突規則，執行實際狀態轉移。

整體流程為：

$$
T_{\mathrm{player}}
\xrightarrow{\mathcal{P}}
A_{\mathrm{IR}}
\xrightarrow{\mathcal{V}}
A_{\mathrm{valid}}
\xrightarrow{\mathcal{S}}
A_{\mathrm{scheduled}}
\xrightarrow{\mathcal{T}}
\Delta W
\xrightarrow{\mathcal{E}}
E
\xrightarrow{\mathcal{N}}
T_{\mathrm{result}}
$$

其中：

- $T_{\mathrm{player}}$：玩家自然語言輸入；
- $\mathcal{P}$：AI 意圖解析與行為編譯；
- $A_{\mathrm{IR}}$：結構化行為中間表示；
- $\mathcal{V}$：前置條件與規則驗證；
- $\mathcal{S}$：行為排程；
- $\mathcal{T}$：狀態轉移；
- $\Delta W$：世界狀態差異；
- $E$：事件集合；
- $\mathcal{N}$：敘事輸出生成。

本文主張，真正可行的架構不是一顆巨大單體 FSM，而是由世界級、區域級、場景級、實體級、系統級與行為級狀態機組成的階層式狀態機群。這些狀態機透過事件總線、狀態差異、優先級與衝突解決策略協同運作。

最終，MUD 不再只是文字指令遊戲，而成為一種以文字介面操作的大型可編譯世界狀態機。

**關鍵詞：** MUD、有限狀態機、階層式狀態機、Action IR、事件溯源、CompilableWorld、AI Agent、自然語言行為、世界狀態機

---

# 第一章　問題提出

## 1.1 傳統 MUD 指令模型的上限

傳統 MUD 通常採用：

```text
verb
verb target
verb target with instrument
```

例如：

```text
look
get sword
open door
attack goblin
unlock door with key
```

這類命令具有明確性、可解析性與低成本，但也存在明顯限制：

1. 行為通常被壓縮為單一步驟；
2. 缺乏時序；
3. 缺乏條件等待；
4. 缺乏並行動作；
5. 缺乏行為方式；
6. 缺乏社會意義；
7. 缺乏意圖與表象差異；
8. 難以表達複合操作；
9. 很難支援高自由度玩家策略。

例如：

```text
open door
```

無法表達：

- 緩慢開門；
- 無聲開門；
- 假裝路過後開門；
- 等守衛轉身再開；
- 與同伴同步開門；
- 用冰凍讓鎖變脆後開門；
- 用身體擋住門避免反鎖。

---

## 1.2 AI 使自然語言行為編譯成為可能

過去若允許玩家自由描述行為，系統將難以穩定解析。

但在 AI 出現後，可以建立：

$$
\mathcal{L}_{\mathrm{natural}}
\xrightarrow{\mathrm{AI}}
\mathcal{A}_{\mathrm{finite}}
$$

其中：

- $\mathcal{L}_{\mathrm{natural}}$ 是開放式自然語言空間；
- $\mathcal{A}_{\mathrm{finite}}$ 是有限且可驗證的行為原語空間。

AI 的作用不是讓規則變得無限，而是把無限表達壓縮為有限操作。

---

## 1.3 核心問題

本文要處理的核心問題是：

> 如何允許玩家使用高自由度自然語言描述複雜行為，同時仍讓世界維持有限、可驗證、可重播與可測試的狀態轉移？

---

# 第二章　正式定位

## 2.1 不是單體巨大 FSM

若直接把整個世界所有狀態組合成單一有限狀態機，將遭遇狀態爆炸。

假設角色有：

- 10 種身體狀態；
- 8 種心理狀態；
- 6 種戰鬥狀態；
- 12 種社交狀態；
- 20 種任務狀態；
- 50 個位置；
- 5 種法律狀態。

則理論組合數為：

$$
10
\times
8
\times
6
\times
12
\times
20
\times
50
\times
5
=
28{,}800{,}000
$$

這還未包含物品、技能、時間、天氣、勢力與其他角色。

因此不可預先列舉所有組合狀態。

---

## 2.2 正確定位

本系統應定義為：

> AI 驅動的階層式、可組合、事件溯源世界狀態機 MUD。

英文可稱：

> AI-Driven Hierarchical Composable World State Machine MUD

其本體為：

$$
\mathcal{W}
=
(
\mathcal{M},
\mathcal{A},
\mathcal{R},
\mathcal{E},
\mathcal{P},
\mathcal{H}
)
$$

其中：

- $\mathcal{M}$：狀態機集合；
- $\mathcal{A}$：行為集合；
- $\mathcal{R}$：轉移規則；
- $\mathcal{E}$：事件集合；
- $\mathcal{P}$：優先級與衝突政策；
- $\mathcal{H}$：事件歷史與狀態來源。

---

# 第三章　階層式世界狀態機

## 3.1 世界分層

世界狀態機分為：

$$
\mathcal{M}
=
\{
M_{\mathrm{world}},
M_{\mathrm{region}},
M_{\mathrm{scene}},
M_{\mathrm{entity}},
M_{\mathrm{system}},
M_{\mathrm{action}}
\}
$$

---

## 3.2 世界級狀態機

管理：

- 世界紀元；
- 全球災難；
- 氣候階段；
- 大型戰爭；
- 世界法則；
- 魔法潮汐；
- 科技階段；
- 全球事件。

示例：

```yaml
world_state:
  era: post_cataclysm
  climate_phase: black_winter
  global_war: dormant
  magic_density: rising
```

---

## 3.3 區域級狀態機

管理：

- 區域控制權；
- 危險；
- 資源；
- 人口；
- 經濟；
- 疫情；
- 派系影響；
- 地區事件。

```yaml
region_state:
  controller: gray_crown_guard
  danger_level: 4
  food_supply: 0.42
  unrest: 0.61
  plague_stage: latent
```

---

## 3.4 場景級狀態機

管理：

- 房間可見性；
- 門窗狀態；
- 火災；
- 光照；
- 聲音；
- 物件位置；
- 陷阱；
- 區域封鎖。

---

## 3.5 實體級狀態機

玩家、NPC、物品與可互動實體均具有多個並行狀態區域。

```yaml
entity_state:
  posture: standing
  locomotion: stationary
  consciousness: awake
  health: wounded
  combat: guarded
  emotion: suspicious
  legal_status: wanted
  social_role: guest
  equipment_mode: sword_drawn
```

此結構可表示為：

$$
S_{\mathrm{entity}}
=
\bigoplus_{i=1}^{n} S_i
$$

其中 $\bigoplus$ 表示多個正交或半獨立狀態區域，而非預先列舉笛卡兒積。

---

## 3.6 系統級狀態機

獨立系統包括：

- 戰鬥；
- 任務；
- 經濟；
- 對話；
- 派系；
- 法律；
- 聲音；
- 光照；
- 天氣；
- 製作；
- 生存；
- 聲望。

系統之間透過事件協作，而不是直接修改彼此內部狀態。

---

# 第四章　State IR

## 4.1 定義

State IR 是所有世界狀態的統一中間表示。

每個 State Definition 應包含：

```text
State ID
Owner Type
Region
Allowed Values
Initial Value
Transition Policy
Persistence
Visibility
Authority
Dependencies
```

---

## 4.2 示例

```yaml
state_definition:
  id: entity.posture
  owner_type: character

  values:
    - standing
    - sitting
    - kneeling
    - prone
    - unconscious

  initial: standing

  persistence: runtime

  transitions:
    standing:
      - sitting
      - kneeling
      - prone
    sitting:
      - standing
      - prone
```

---

## 4.3 狀態可見性

不同狀態具有不同可見層級：

```text
public
observable
inferred
private
system_only
```

例如：

- 姿勢是公開的；
- 是否受傷可被觀察；
- 心理懷疑只能推測；
- 任務旗標是私人；
- 內部 AI 排程是系統專用。

---

# 第五章　Action IR

## 5.1 行為不是字串

玩家輸入：

> 等守衛轉身後，用藏在衣服裡的鑰匙無聲開門。

AI 應轉換為：

```yaml
action_sequence:
  actor: player_001

  steps:
    - action: wait_for
      condition:
        target: guard_001
        field: facing
        operator: not_equal
        value: player_001

    - action: retrieve
      target: key_old_vault
      source: clothing_inner
      hand: left
      concealment: true

    - action: unlock
      target: door_014
      instrument: key_old_vault
      mode: silent
```

---

## 5.2 Action IR 的正式結構

$$
A
=
(
\alpha,
v,
\tau,
\iota,
\mu,
\theta,
\pi,
\kappa,
\epsilon,
\phi
)
$$

其中：

- $\alpha$：Actor；
- $v$：Verb；
- $\tau$：Target；
- $\iota$：Instrument；
- $\mu$：Method；
- $\theta$：Timing；
- $\pi$：Preconditions；
- $\kappa$：Costs；
- $\epsilon$：Effects；
- $\phi$：Failure Effects。

---

## 5.3 Action Primitive

底層應保留有限原語：

```text
move
observe
wait
hold
release
apply_force
damage
heal
unlock
open
close
hide
reveal
speak
deceive
trade
equip
use
combine
cast
coordinate
```

複合行為由原語組成。

---

# 第六章　行為編譯管線

## 6.1 自然語言解析

```text
玩家語句
→ 意圖
→ 行為候選
→ 實體解析
→ 時序解析
→ 方法解析
→ Action IR
```

---

## 6.2 歧義處理

若玩家說：

```text
打開它
```

系統可能需要解析：

- 哪一個目標？
- 使用手還是工具？
- 正常還是無聲？
- 是否先移動到目標旁？

AI 可提出補全候選，但不可捏造高風險意圖。

---

## 6.3 驗證

Action Validator 檢查：

- Actor 是否存在；
- Target 是否可見；
- Instrument 是否持有；
- 距離是否足夠；
- 角色狀態是否允許；
- 資源是否足夠；
- 行為是否被環境禁止；
- 是否違反世界公理；
- 是否需要進一步分解。

---

# 第七章　Transition Rule

## 7.1 形式

轉移規則表示為：

$$
r:
(S,A,C)
\rightarrow
(S',E,O)
$$

其中：

- $S$：原狀態；
- $A$：行為；
- $C$：條件與上下文；
- $S'$：新狀態；
- $E$：事件；
- $O$：直接輸出。

---

## 7.2 示例

```yaml
rule:
  id: unlock_door_with_key

  when:
    action.type: unlock
    target.type: door
    instrument.type: key

  require:
    - actor.has(instrument)
    - target.locked == true
    - instrument.key_code == target.lock_code

  effects:
    - set target.locked = false

  emit:
    - door_unlocked
```

---

## 7.3 失敗規則

```yaml
failure:
  when:
    - actor.skill.lockpicking < target.difficulty

  effects:
    - action.state = failed
    - target.alert_level += 1

  emit:
    - lockpick_failed
    - noise_generated
```

---

# 第八章　Event IR

## 8.1 事件是跨系統協作介面

門被打開不只是布林值變更。

```yaml
event:
  id: event_184220
  type: door_opened
  actor: player_001
  target: door_014
  method: hidden_key
  location: corridor_003
  sound_level: 2
  visibility: local
  legal_status: trespassing
  timestamp: 184220
```

---

## 8.2 訂閱者

```text
Door System
Sound System
Guard AI
Law System
Quest System
Narrative Renderer
Audit Log
```

---

## 8.3 事件溯源

世界狀態可由 Snapshot 與事件重建：

$$
W_t
=
\operatorname{Fold}
(
W_{t_0},
E_{t_0+1},
\ldots,
E_t
)
$$

這允許：

- 重播；
- 回滾；
- Debug；
- AI 玩家分析；
- 世界分支；
- 因果追蹤。

---

# 第九章　行為自身的狀態機

## 9.1 複合行為具有生命週期

```text
proposed
→ parsed
→ validated
→ queued
→ executing
→ interrupted
→ resumed
→ completed
→ failed
→ cancelled
```

---

## 9.2 長時間行為

適用於：

- 撬鎖；
- 治療；
- 鍛造；
- 施法；
- 閱讀；
- 搜索；
- 談判；
- 長距離移動。

```yaml
action_instance:
  id: pick_lock_001
  state: executing
  duration: 8
  progress: 3

  interrupt_when:
    - actor.takes_damage
    - target.moves
    - actor.tool_missing
    - actor.concentration < 20
```

---

# 第十章　並行、衝突與優先級

## 10.1 同步衝突

同一時間可能發生：

- 玩家關門；
- NPC 開門；
- 火焰摧毀門；
- 爆炸破壞牆；
- 任務事件鎖定區域。

因此不能依賴任意執行順序。

---

## 10.2 衝突政策

需要定義：

- Priority；
- Atomicity；
- Lock；
- Interrupt；
- Rollback；
- Merge；
- Last-Writer；
- Domain Authority。

---

## 10.3 示例

```yaml
conflict_policy:
  resource: door_014

  precedence:
    destruction: 100
    system_lock: 80
    close: 40
    open: 40

  tie_breaker:
    - initiative
    - timestamp
    - actor_id
```

---

## 10.4 狀態差異

所有行為先產生 Delta：

```yaml
delta:
  target: door_014
  field: state
  from: closed
  to: open
  authority: player_action
  priority: 40
```

再由衝突解決器決定最終提交。

---

# 第十一章　敘事輸出

## 11.1 規則結果與文字分離

底層結果：

```yaml
result:
  success: true
  events:
    - door_unlocked
    - door_opened
    - low_noise_generated
```

敘事層可輸出：

> 你等到守衛轉身，悄悄抽出藏在衣內的鑰匙。鎖舌輕輕一響，門無聲地滑開了一道縫。

---

## 11.2 不可讓敘事改寫結果

Narrative Renderer 只能表達已確定結果，不能自行：

- 增加物品；
- 改變傷害；
- 宣稱 NPC 沒有察覺；
- 新增任務成功；
- 改寫世界公理。

---

# 第十二章　CompilableWorld 的擴張

## 12.1 不只編譯世界資料

完整 CompilableWorld 應包含：

$$
\mathrm{CompilableWorld}
=
D
+
S
+
A
+
T
+
E
+
P
+
H
$$

其中：

- $D$：世界資料；
- $S$：狀態定義；
- $A$：行為定義；
- $T$：轉移規則；
- $E$：事件契約；
- $P$：優先級與衝突政策；
- $H$：歷史與事件溯源規則。

---

## 12.2 JSON／CSV／EML 分工

```text
CSV：大量狀態值、行為參數、技能、物品、房間
JSON：巢狀規則、事件、任務、狀態機
EML：高密度語義、條件、轉移、生命週期、Patch
```

---

# 第十三章　AI 的責任邊界

## 13.1 AI 可以做

- 自然語言解析；
- 行為候選生成；
- 目標與工具解析；
- 複合行為分解；
- 低風險參數補全；
- 敘事輸出；
- 測試策略；
- 錯誤分析。

---

## 13.2 AI 不應直接做

- 自行決定高風險成功；
- 跳過前置條件；
- 改寫世界公理；
- 直接寫入正式狀態；
- 自行處理衝突結果；
- 自行批准程式修改；
- 依敘事需要創造不存在的事實。

---

# 第十四章　第一版應先完成的五個核心規格

## 14.1 State IR

定義：

- 世界；
- 區域；
- 場景；
- 實體；
- 系統；
- 行為。

---

## 14.2 Action IR

定義：

- Actor；
- Verb；
- Target；
- Instrument；
- Method；
- Timing；
- Preconditions；
- Costs；
- Effects；
- Failure。

---

## 14.3 Transition Rule

定義：

$$
(S,A,C)
\rightarrow
(S',E)
$$

---

## 14.4 Event IR

定義所有跨系統通知。

---

## 14.5 Conflict Resolution

定義：

- Priority；
- Atomicity；
- Interrupt；
- Rollback；
- Merge；
- Tie Breaker。

---

# 第十五章　MVP 路線

## Phase 0：最小狀態核心

只支援：

- 姿勢；
- 位置；
- 門；
- 持有物；
- 基本生命值；
- 行為排程。

---

## Phase 1：Action IR

先支援：

```text
move
observe
take
drop
open
close
unlock
wait
attack
speak
```

---

## Phase 2：複合行為

支援：

- Sequential；
- Conditional；
- Wait；
- Interrupt；
- Retry；
- Cancel。

---

## Phase 3：事件系統

加入：

- 聲音；
- 可見性；
- 法律；
- 任務；
- NPC 反應。

---

## Phase 4：AI 自然語言編譯

AI 只把自然語言轉為 Action IR，不直接執行。

---

## Phase 5：多 Agent 與大型世界

加入：

- 多玩家；
- NPC Agent；
- AI 測試玩家；
- 區域狀態機；
- 世界級事件。

---

# 第十六章　測試策略

## 16.1 Action IR 測試

- 指令解析；
- 歧義；
- 缺失參數；
- 不存在目標；
- 不合法工具；
- 前置條件失敗。

---

## 16.2 Transition 測試

- 成功；
- 失敗；
- 中斷；
- 回滾；
- 並行；
- 競態。

---

## 16.3 Event 測試

- 訂閱；
- 重複事件；
- 順序；
- 遺失；
- 回放；
- Snapshot 還原。

---

## 16.4 AI 測試

- 同義句；
- 複合句；
- 故意模糊；
- 惡意越權；
- 敘事誘導；
- 不存在能力。

---

# 第十七章　反模式

## 17.1 單體巨大 FSM

所有狀態組合在一起，造成狀態爆炸。

## 17.2 AI 直接裁決結果

會破壞可重播與可測試性。

## 17.3 行為直接改狀態

缺少事件、審計與跨系統協作。

## 17.4 敘事層決定規則

文字生成不應改寫世界真實狀態。

## 17.5 所有行為瞬間完成

會失去中斷、時序與策略。

## 17.6 沒有衝突解決

多人與多 Agent 世界將產生不可重現結果。

---

# 第十八章　理論意義

## 18.1 MUD 成為世界操作介面

MUD 不再只是遊戲類型，而是：

> 對大型世界狀態機進行自然語言操作的介面。

---

## 18.2 AI 成為語言編譯器

AI 的核心角色不是自由寫故事，而是：

$$
\text{Natural Language}
\rightarrow
\text{Finite Action Space}
$$

---

## 18.3 世界成為可計算狀態歷史

世界不只是地圖與文本，而是：

$$
W_t
=
W_0
+
\sum_{i=1}^{t}\Delta W_i
$$

並且每個 $\Delta W_i$ 都可追溯至行為與事件。

---

# 第十九章　結論

本文提出一種超大型階層式有限狀態世界 MUD。

其核心不在於建立更長的文字描述，也不在於讓 AI 任意決定遊戲結果，而在於建立以下閉環：

```text
自然語言
→ AI 行為編譯
→ Action IR
→ 驗證
→ 排程
→ 階層式狀態機
→ 事件
→ 世界差異
→ 敘事輸出
```

真正的系統本體是：

> 一組可組合、可並行、可中斷、可回滾、可事件溯源的世界狀態機。

AI 使玩家可以使用高度自由的語言表達，但底層仍保持有限行為原語與確定性規則。

因此，本專案不只是一般 MUD，而是：

> AI 驅動的自然語言可編譯世界狀態機遊戲。

---

# 附錄 A　最小 Action IR

```yaml
action:
  id: action_001
  actor: player_001
  verb: unlock
  target: door_014
  instrument: key_old_vault
  method:
    stealth: true
    hand: left
  timing:
    after:
      condition: guard_001.facing != player_001
  preconditions:
    - actor.has(instrument)
    - actor.distance(target) <= 1
  cost:
    stamina: 1
  success:
    - target.locked = false
  failure:
    - emit noise_generated
```

---

# 附錄 B　最小 Event IR

```yaml
event:
  id: event_001
  type: door_unlocked
  source_action: action_001
  actor: player_001
  target: door_014
  location: corridor_003
  timestamp: 184220
  visibility: local
  sound_level: 1
  subscribers:
    - door_system
    - guard_ai
    - law_system
    - quest_system
    - narrative_renderer
```

---

# 附錄 C　第一版實作清單

- [ ] State IR Schema
- [ ] Action IR Schema
- [ ] Event IR Schema
- [ ] Transition Rule Schema
- [ ] Conflict Policy Schema
- [ ] Action Parser
- [ ] Action Validator
- [ ] Action Scheduler
- [ ] State Store
- [ ] Event Bus
- [ ] Delta Committer
- [ ] Narrative Renderer
- [ ] Snapshot
- [ ] Event Log
- [ ] Replay
- [ ] AI Natural Language Adapter
- [ ] AI Player Test Suite
