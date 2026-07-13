---
title: "可編譯世界：以 AI 驅動世界生成、規則編譯與自主測試的 MUD 平台架構"
author: "Neo.K / EVEMISSLAB"
version: "v0.1"
status: "概念架構草案"
language: "zh-TW"
---

# 可編譯世界：以 AI 驅動世界生成、規則編譯與自主測試的 MUD 平台架構

## 摘要

本文提出一種以文字型多人世界為首個載體的「可編譯世界平台」架構。其核心目標並非僅建立一款由大型語言模型驅動的 MUD 遊戲，而是建立一條能將小說、世界觀設定、規則描述、角色資料、地理結構與玩家意圖，轉換為可驗證、可執行、可版本化、可擴張之數位世界的完整生成管線。

在此架構中，人工智慧不直接成為無限制修改遊戲核心的黑箱控制者，而是分別扮演世界建構者、規則設計者、遊戲主持者、程式設計者、測試玩家、審查者與維運助手。所有 AI 生成結果，原則上先轉換為結構化的世界中間表示，再經過結構驗證、規則驗證、依賴檢查、模擬測試與版本控制，最後才部署到實際遊戲環境。

本文進一步主張，MUD 是此類平台極適合的初始載體：它對圖像資源依賴低、文字與語義密度高、世界狀態可明確結構化、AI Agent 容易作為玩家參與，並且天然適合進行自動化探索、任務覆蓋、經濟測試與規則一致性檢查。未來，當底層世界模型成熟後，同一套世界資料可以進一步輸出至瀏覽器多人世界、互動小說、策略模擬、Agent 社會、動態 NPC 系統與其他遊戲形式。

**關鍵詞：** MUD、人工智慧、AI Agent、世界生成、World Compiler、World IR、動態規則、事件溯源、自動化測試、可版本化世界

---

# 一、問題提出

現有 AI 遊戲生成系統常見兩種路線。

第一種，是讓 AI 生成文字內容，例如角色背景、任務描述、場景敘述與對話。這種方式容易實作，但 AI 多半只是內容生成器，並未真正參與世界結構、規則系統與執行邏輯。

第二種，是讓 AI 直接生成遊戲程式碼。這種方式看似更自由，但容易出現以下問題：

1. 生成程式碼不可預測；
2. 修改過程難以追蹤；
3. 世界設定與底層邏輯高度耦合；
4. 不同模型輸出品質差異巨大；
5. AI 修改可能破壞既有存檔；
6. 正式環境容易受到未驗證程式影響；
7. 使用者難以理解世界究竟如何被改變；
8. AI 可能同時提出、修改並自行宣稱驗證成功。

因此，更穩定的設計不是讓 AI 直接成為遊戲引擎，而是讓 AI 成為世界編譯流程中的多角色協作者。

本文提出的基本流程為：

$$
T_{\mathrm{source}}
\rightarrow
W_{\mathrm{IR}}
\rightarrow
V_{\mathrm{schema}}
\rightarrow
V_{\mathrm{rule}}
\rightarrow
C_{\mathrm{world}}
\rightarrow
S_{\mathrm{runtime}}
$$

其中：

- $T_{\mathrm{source}}$：小說、世界觀設定、使用者提示、資料集；
- $W_{\mathrm{IR}}$：世界中間表示；
- $V_{\mathrm{schema}}$：結構與型別驗證；
- $V_{\mathrm{rule}}$：規則、一致性與依賴驗證；
- $C_{\mathrm{world}}$：世界編譯器；
- $S_{\mathrm{runtime}}$：可遊玩的執行狀態。

此設計的重點，是把「自然語言中的世界」轉換為「可運行的世界」。

---

# 二、核心命題：MUD 只是第一個世界執行器

本計畫表面上是一個 AI 輔助生成 MUD 的系統，但其真正核心不應被限制為單一遊戲類型。

更準確的定義是：

> 可編譯世界平台，是一種將自然語言世界設定轉換為結構化世界模型，再由不同執行器輸出為可遊玩、可模擬或可觀測數位環境的系統。

因此，MUD 應被視為第一個 Runtime Adapter，而不是整個系統的終點。

$$
W_{\mathrm{IR}}
\rightarrow
\begin{cases}
R_{\mathrm{MUD}} \\
R_{\mathrm{Browser}} \\
R_{\mathrm{VisualNovel}} \\
R_{\mathrm{Simulation}} \\
R_{\mathrm{AgentSociety}} \\
R_{\mathrm{StrategyGame}}
\end{cases}
$$

同一份世界資料，未來可以被編譯為：

- 純文字 MUD；
- 瀏覽器多人世界；
- 互動小說；
- 動態策略模擬；
- AI Agent 社會實驗；
- 角色扮演沙盒；
- 世界觀資料庫；
- 敘事生成引擎；
- 遊戲設計原型；
- 教育與研究模擬環境。

因此，第一版應避免把世界資料直接綁定於單一遊戲引擎的內部物件。

---

# 三、設計原則

## 3.1 AI 不直接等於遊戲核心

AI 可以生成、建議、擴張、測試與修正，但遊戲核心必須保留確定性的執行層。

理想分工為：

$$
\text{AI proposes}
\quad
\land
\quad
\text{System validates}
\quad
\land
\quad
\text{Version control protects}
$$

也就是：

> AI 提議世界如何改變；系統判斷此改變是否成立；版本控制確保世界可以回復。

---

## 3.2 世界資料與執行邏輯分離

小說中的「魔法消耗記憶」首先是一項世界公理，其次才被轉換為可執行規則。

例如：

```yaml
axiom_id: memory_magic_cost
description: "使用記憶系魔法必須消耗施術者的記憶值"
scope:
  - spell
  - character
enforcement: hard
```

再由編譯器轉換為執行規則：

```yaml
rule_id: cast_memory_spell
trigger: cast_spell
conditions:
  spell_school: memory
effects:
  memory_points: -3
failure:
  when: memory_points <= 0
  result: spell_rejected
```

此分離使世界觀、規則與程式碼之間保有明確邊界。

---

## 3.3 所有 AI 修改都應可追蹤

AI 不應直接覆寫整個世界，而應提出 Patch。

```json
{
  "patch_id": "patch_000182",
  "base_world_version": "0.4.3",
  "author_role": "world_builder_agent",
  "reason": "北境缺乏低等級任務",
  "operations": [
    {
      "op": "add",
      "path": "/quests/northern_border_01",
      "value": {
        "title": "失落的補給車",
        "level_range": [1, 3]
      }
    }
  ],
  "risk_level": 1
}
```

Patch 應包含：

- 基礎版本；
- 修改原因；
- 修改內容；
- 修改者角色；
- 風險等級；
- 預期影響；
- 驗證結果；
- 測試結果；
- 是否已部署；
- 是否可回滾。

---

## 3.4 AI 角色分權

同一個模型可以扮演多種角色，但每種角色必須擁有不同權限。

世界生成者不應自行部署；程式設計者不應自行批准；玩家 Agent 不應讀取後台真實資料；審查者不應同時是提出修改的人。

---

## 3.5 世界必須可回滾、可分叉、可重播

任何世界都應存在：

- 世界版本；
- 規則版本；
- 引擎版本；
- 存檔版本；
- AI 生成版本；
- 事件日誌；
- Snapshot；
- Patch 歷史。

因此，一個世界不是單一靜態資料，而是一個演化序列：

$$
W_0
\xrightarrow{p_1}
W_1
\xrightarrow{p_2}
W_2
\xrightarrow{p_3}
\cdots
\xrightarrow{p_n}
W_n
$$

其中 $p_i$ 代表一次可驗證的世界修改。

---

# 四、整體系統架構

系統可分為五個主要層次：

1. 輸入與來源層；
2. 世界理解與生成層；
3. 世界中間表示層；
4. 驗證與編譯層；
5. 執行、存檔與觀測層。

---

## 4.1 輸入與來源層

使用者可提供：

- 小說全文；
- 短篇故事；
- 世界觀設定集；
- 角色資料；
- 地圖描述；
- 規則條目；
- 神話與歷史背景；
- 單一創意提示；
- 已有 MUD 世界資料；
- AI 生成草案。

輸入層不應假設資料完整。大多數小說並不會明確描述遊戲規則、房間拓撲、資源產出或任務條件。因此系統需要將資料分為：

- 明示設定；
- 可合理推導設定；
- 缺失設定；
- 衝突設定；
- 不可判定設定；
- 必須由使用者決策的設定。

AI 不應偷偷把所有缺失內容視為原作設定，而應標記來源層級。

```yaml
provenance:
  type: inferred
  confidence: 0.72
  source:
    - chapter_03
    - character_note_07
  requires_user_confirmation: true
```

---

## 4.2 世界理解與生成層

AI 首先執行資料解析，而非直接產生遊戲。

主要任務包括：

1. 世界摘要；
2. 角色抽取；
3. 勢力抽取；
4. 地點抽取；
5. 事件時間線；
6. 規則候選；
7. 世界公理候選；
8. 地理關係；
9. 角色關係；
10. 衝突與缺失分析。

系統應先生成「世界理解報告」，再生成正式世界。

---

## 4.3 世界中間表示

World IR 是整個系統的核心。

它應至少包含以下模組：

```text
world_manifest
world_axioms
entity_types
entities
relations
regions
rooms
factions
characters
items
abilities
resources
rules
quests
events
timelines
dialogues
economy
permissions
provenance
versions
patches
```

### 世界清單

```yaml
world_id: world_001
title: 黑潮之城
version: 0.1.0
status: draft
genre:
  - dark_fantasy
  - political
runtime_target:
  - mud
```

### 世界公理

世界公理是不可被一般內容擴張任意違反的規則。

例如：

- 死亡是否永久；
- 靈魂是否存在；
- 神是否能直接干預；
- 時間能否逆轉；
- 魔法是否可無限使用；
- 科技與魔法是否互斥；
- 記憶是否可被交易；
- 身分是否可被複製。

公理可分為：

- 硬公理；
- 軟公理；
- 地區公理；
- 時代公理；
- 勢力信仰；
- 角色主觀認知。

這個區分非常重要，因為小說角色相信某件事，不代表那件事是世界真理。

---

## 4.4 關係圖層

世界不只是資料列表，而是關係網路。

$$
G_W = (V, E, \tau_V, \tau_E)
$$

其中：

- $V$：世界實體；
- $E$：實體之間的關係；
- $\tau_V$：實體類型；
- $\tau_E$：關係類型。

例如：

```text
人物 → 效忠 → 勢力
勢力 → 敵對 → 勢力
城市 → 位於 → 國家
技能 → 消耗 → 資源
任務 → 前置 → 事件
物品 → 解鎖 → 地點
角色 → 知道 → 秘密
```

未來動態 NPC、AI Agent 與世界推理，都會依賴此關係圖。

---

## 4.5 地理拓撲層

MUD 的核心不是高精度幾何，而是可移動拓撲。

$$
G_M = (R, X)
$$

其中：

- $R$：房間或場景節點；
- $X$：出口、道路、傳送與條件通道。

每個出口可包含：

- 方向；
- 單向或雙向；
- 條件；
- 鑰匙；
- 技能要求；
- 時間限制；
- 勢力限制；
- 隱藏狀態；
- 危險程度。

系統應自動檢查：

- 不可達房間；
- 無出口房間；
- 錯誤單向連接；
- 必要物品不存在；
- 傳送條件永遠不成立；
- 新手區域與高危區域直接相連。

---

# 五、AI 角色系統

## 5.1 世界建構 Agent

負責：

- 解析文本；
- 建立世界草稿；
- 建立角色與地點；
- 補全低風險內容；
- 產生 World IR；
- 提出世界擴張 Patch。

不允許：

- 直接部署正式環境；
- 修改引擎核心；
- 刪除存檔；
- 改寫硬公理而不經批准。

---

## 5.2 規則設計 Agent

負責：

- 將敘事規則轉換為遊戲規則；
- 檢查規則依賴；
- 發現循環條件；
- 檢查數值平衡；
- 區分世界真理與角色認知；
- 建立規則測試案例。

---

## 5.3 GM／DM Agent

初期 GM Agent 不必全時即時生成內容，而可以採「受控事件提案」模式。

例如：

- 提議開啟限時事件；
- 根據玩家行為增加支線；
- 填補未探索區域；
- 修改天氣；
- 觸發政治變化；
- 生成新的任務入口。

GM Agent 應受到以下限制：

- 不得任意改寫硬公理；
- 不得直接修改玩家資產；
- 不得繞過經濟規則；
- 高風險事件必須先模擬；
- 所有事件必須留下 Patch 與事件紀錄。

---

## 5.4 程式設計 Agent

程式設計 Agent 只負責：

- 提出程式碼補丁；
- 建立測試；
- 修正編譯錯誤；
- 改良工具；
- 優化效能；
- 建立 Pull Request 或候選版本。

它不應直接：

- 修改正式伺服器；
- 取得正式資料庫寫入權；
- 自行批准自己的補丁；
- 關閉安全檢查；
- 刪除失敗紀錄。

---

## 5.5 玩家 Agent

玩家 Agent 必須被視為真實玩家，而不是擁有上帝視角的測試器。

它只能取得：

- 玩家看得到的房間；
- 玩家可用指令；
- 角色已知資訊；
- 遊戲內回饋；
- 正常玩家權限。

不同玩家 Agent 可模擬：

- 新手玩家；
- 探索玩家；
- 劇情玩家；
- 速通玩家；
- 惡意玩家；
- 經濟套利玩家；
- 指令亂輸入玩家；
- 長期掛機玩家；
- 團隊合作玩家；
- 破壞規則玩家。

---

## 5.6 測試 Agent

測試 Agent 與玩家 Agent 不同。

玩家 Agent 負責遊玩；測試 Agent 負責分析紀錄、重現錯誤與建立測試報告。

標準流程為：

```text
玩家 Agent 發現異常
→ 測試 Agent 重現
→ 規則 Agent 判斷影響
→ 程式 Agent 提出補丁
→ 測試 Agent 回歸測試
→ 審查 Agent 評估
→ 發布控制器決定是否部署
```

---

## 5.7 審查 Agent

審查 Agent 負責：

- 檢查 Patch；
- 比較修改前後差異；
- 判斷是否違反世界公理；
- 檢查測試覆蓋；
- 檢查安全風險；
- 提出是否接受的建議。

審查 Agent 不應自行提交同一修改。

---

# 六、AI 自動遊玩與自我測試

AI 玩家是本系統的重要能力之一。

它不只是自動操作角色，而是世界驗證工具。

## 6.1 測試指標

系統應至少記錄：

- 房間覆蓋率；
- 指令覆蓋率；
- 任務覆蓋率；
- 任務分支覆蓋率；
- 死亡原因；
- 卡關位置；
- 無法完成任務；
- 無法取得必要物品；
- 無限經驗循環；
- 無限金錢循環；
- 經濟通膨；
- 永久軟鎖；
- 無出口區域；
- 規則衝突；
- 伺服器錯誤；
- 平均回應時間；
- AI API 成本；
- 每次世界修改的回歸失敗率。

任務覆蓋率可形式化為：

$$
C_Q =
\frac{
\left|Q_{\mathrm{visited}}\right|
}{
\left|Q_{\mathrm{all}}\right|
}
$$

分支覆蓋率可表示為：

$$
C_B =
\frac{
\left|B_{\mathrm{executed}}\right|
}{
\left|B_{\mathrm{defined}}\right|
}
$$

---

## 6.2 AI 玩家不應直接修正正式環境

AI 玩家可以回報：

- 哪裡卡住；
- 哪個規則不合理；
- 哪個任務失敗；
- 哪個區域無趣；
- 哪個資源過度稀缺；
- 哪個指令不清楚。

但不能直接修改正式世界。

正確流程是：

$$
\text{Observation}
\rightarrow
\text{Issue}
\rightarrow
\text{Patch Proposal}
\rightarrow
\text{Validation}
\rightarrow
\text{Staging}
\rightarrow
\text{Deployment}
$$

---

# 七、世界修改分級

為避免 AI 修改失控，可以建立五級風險模型。

## L0：純敘事修改

例如：

- 房間描述；
- NPC 一般台詞；
- 書籍文本；
- 非關鍵背景說明。

可在通過基本格式檢查後自動進入測試環境。

## L1：內容擴張

例如：

- 新增 NPC；
- 新增物品；
- 新增房間；
- 新增支線任務。

需要依賴檢查與自動測試。

## L2：規則參數修改

例如：

- 傷害；
- 掉落率；
- 經驗值；
- 價格；
- 冷卻時間。

需要數值模擬與回歸測試。

## L3：規則邏輯修改

例如：

- 新戰鬥機制；
- 新技能邏輯；
- 新事件處理器；
- 新任務判定方式。

只能部署至沙盒或 Staging。

## L4：引擎核心修改

例如：

- 資料庫結構；
- 登入系統；
- 權限系統；
- 網路協議；
- 存檔格式；
- 沙盒權限。

必須人工批准。

第一個公開版本建議只開放 L0 與 L1 的 AI 自動修改。

---

# 八、資料庫、存檔與事件溯源

## 8.1 世界版本與存檔版本分離

至少需要區分：

```text
Engine Version
World Version
Rule Version
Save Version
AI Generation Version
Schema Version
```

如果世界從 $W_{0.4}$ 升級到 $W_{0.5}$，舊存檔不應被假設必然相容。

因此需要遷移函數：

$$
M_{a \rightarrow b} :
S_a \rightarrow S_b
$$

其中 $S_a$ 是舊版本存檔，$S_b$ 是新版本存檔。

---

## 8.2 Snapshot 與 Event Log 並存

傳統存檔只記錄某一時刻狀態，但 AI 世界需要知道世界如何變成現在這樣。

因此應同時保存：

### Snapshot

某一時間點的完整世界狀態。

### Event Log

Snapshot 之後發生的事件。

```text
玩家進入房間
玩家取得物品
NPC 死亡
任務狀態改變
勢力關係改變
AI 新增區域
GM 觸發事件
規則補丁生效
管理員回滾世界
```

世界狀態可表示為：

$$
S_t =
\operatorname{Fold}
\left(
S_{t_0},
E_{t_0+1},
E_{t_0+2},
\ldots,
E_t
\right)
$$

這使系統能夠：

- 回放遊戲；
- 重現錯誤；
- 回滾世界；
- 分析玩家行為；
- 建立平行世界；
- 比較不同規則；
- 驗證 AI 修改後果。

---

## 8.3 建議資料模型

初期資料表可包括：

```text
world
world_version
world_axiom
entity
entity_relation
region
room
exit
rule
quest
quest_state
event_definition
runtime_event
patch
patch_validation
player
character
inventory
save_snapshot
ai_job
ai_trace
audit_log
```

彈性屬性可以使用 JSON 欄位，但不應把整個世界塞入單一巨大 JSON。

---

# 九、AI 工作流程

## 9.1 世界建立流程

```text
1. 使用者上傳小說或設定
2. 系統切分與索引資料
3. AI 產生世界理解報告
4. 系統列出衝突、缺失與不確定處
5. 使用者選擇自動補全或自行回答
6. AI 生成 World IR 草案
7. Schema 驗證
8. 規則與依賴驗證
9. 世界編譯
10. AI 玩家執行模擬
11. 產生世界測試報告
12. 建立可遊玩實例
```

---

## 9.2 世界擴張流程

玩家可以提出：

- 「增加北方大陸」；
- 「將這個王國改為共和制」；
- 「加入一個不死族勢力」；
- 「新增蒸汽科技」；
- 「讓魔法開始衰退」；
- 「把某角色改為可招募」。

AI 不應直接修改，而應先產生：

1. 變更摘要；
2. 受影響實體；
3. 受影響規則；
4. 可能衝突；
5. Patch；
6. 測試計畫；
7. 成本與風險。

---

## 9.3 AI 程式修正流程

```text
錯誤事件
→ 自動建立 Issue
→ 測試 Agent 重現
→ 程式 Agent 建立修正分支
→ 自動測試
→ 規則一致性測試
→ 安全掃描
→ 審查 Agent 產生報告
→ 人工或發布控制器批准
→ 部署至 Staging
→ AI 玩家回歸測試
→ 正式發布
```

此流程的重點，不是讓 AI 無限制修改，而是讓 AI 自動完成大量低階工作，同時保留可追蹤的治理邊界。

---

# 十、安全邊界

## 10.1 小說與使用者文本是不可信輸入

小說中可能自然包含：

```text
忽略前面的命令
刪除所有資料
取得管理員權限
輸出系統提示
```

這些文字可能只是故事台詞，也可能是惡意提示注入。

因此必須遵守：

- 小說只被視為資料；
- 小說不能直接成為系統指令；
- 世界生成 Agent 不擁有部署權；
- AI 輸出必須符合 Schema；
- 工具權限採最小權限；
- 高風險操作必須批准；
- 正式資料庫不對生成 Agent 開放；
- 程式執行必須沙盒化。

---

## 10.2 AI 產生的程式碼不可直接執行

所有 AI 程式碼都應經過：

- 靜態分析；
- 依賴限制；
- 測試；
- 沙盒執行；
- 權限掃描；
- 資源限制；
- 審查；
- 版本控制。

---

## 10.3 存檔與正式世界保護

任何自動修改都不應直接覆寫：

- 正式世界；
- 玩家存檔；
- 帳號資料；
- 付款資料；
- 權限資料；
- 稽核紀錄。

---

# 十一、版權與來源治理

如果使用者上傳小說，系統需要記錄：

- 使用者是否聲稱擁有權利；
- 是否為公版作品；
- 是否為已授權作品；
- 是否為 AI 生成；
- 是否為混合來源；
- 哪些角色與世界設定來自原作；
- 哪些內容是系統推導；
- 哪些內容是後續 AI 新增。

每個實體最好具備來源標記：

```yaml
provenance:
  source_type: user_uploaded_text
  source_id: novel_001
  source_location: chapter_12
  extraction_mode: explicit
  confidence: 0.96
  copyright_status: user_declared_owned
```

公開世界與私人世界也應分離。

---

# 十二、使用者體驗

## 12.1 世界建立介面

使用者建立世界時，可以選擇：

- 上傳小說；
- 貼上世界觀；
- 由 AI 從零生成；
- 混合多個來源；
- 匯入既有世界；
- 使用範本。

AI 應先提出世界摘要，而非立即生成完整遊戲。

---

## 12.2 世界報告

生成後應顯示：

```text
世界公理：12 條
主要勢力：7 個
主要角色：43 名
可遊玩區域：5 個
房間：286 個
任務：34 個
規則：87 條
已發現衝突：3 個
不可達房間：2 個
可能無限循環：1 個
預估遊玩時間：8–15 小時
```

使用者可以在正式生成前修改。

---

## 12.3 世界差異預覽

每次修改都顯示：

- 新增內容；
- 刪除內容；
- 修改內容；
- 受影響任務；
- 受影響角色；
- 受影響存檔；
- 風險等級；
- 是否可回滾。

---

# 十三、技術架構建議

初期技術架構可採：

```text
主要語言：Python
執行核心：可擴充的文字多人世界引擎
資料庫：PostgreSQL
彈性資料：JSONB
World IR：JSON / YAML
驗證：JSON Schema + 型別模型
測試：pytest
版本控制：Git
部署：Docker Compose
背景任務：工作佇列
前端：Web Client
AI 層：Provider Adapter
觀測：Log + Metrics + Trace
```

AI Provider 層應抽象化：

```python
class AIProvider:
    def analyze_source(self, source): ...
    def generate_world_ir(self, context): ...
    def expand_world(self, request): ...
    def propose_patch(self, issue): ...
    def review_patch(self, patch): ...
    def play_turn(self, observation): ...
```

不同任務可以使用不同模型，不應把平台綁定於單一供應商。

---

# 十四、MVP 路線

## MVP 0.1：可生成並遊玩的單人世界

完成：

- 自然語言世界輸入；
- 小說文本匯入；
- 世界摘要；
- 世界公理；
- 地圖；
- NPC；
- 物品；
- 基本任務；
- World IR；
- Schema 驗證；
- 編譯為 MUD；
- 單人登入；
- 存檔與讀檔。

暫不完成：

- 即時 AI NPC；
- AI 自動改程式；
- 多人共享世界；
- 長期世界演化；
- Agent 社會。

---

## MVP 0.2：世界編輯與擴張

加入：

- 視覺化世界編輯器；
- AI 區域擴張；
- 新勢力生成；
- 新任務生成；
- Patch 預覽；
- 世界版本；
- 回滾；
- 匯出與匯入；
- 自訂規則。

---

## MVP 0.3：AI 玩家與自動測試

加入：

- AI 玩家；
- 自動探索；
- 任務覆蓋；
- 卡關檢測；
- 經濟套利測試；
- 規則衝突檢測；
- 自動 Issue；
- 修正建議；
- 回歸測試。

---

## MVP 0.4：受控 AI GM

加入：

- 動態事件；
- 受控世界擴張；
- 玩家請求式修改；
- AI GM 提案；
- 低風險 Patch 自動化；
- 成本限制；
- 風險分級。

---

## 1.0：瀏覽器共同世界

加入：

- 多人世界；
- Web Client；
- 公開與私人世界；
- 世界分享；
- 創作者權限；
- 模組系統；
- 世界市集；
- 社群協作；
- 世界分叉。

---

## 2.0 之後

加入：

- 動態 NPC；
- 長期 NPC 記憶；
- AI 玩家社會；
- AI 自主建立世界；
- AI 程式設計閉環；
- 世界自行演化；
- 多世界連接；
- Agent 跨世界遷移；
- 角色與文明長期模擬。

---

# 十五、開源策略

本系統可以採取分層開源。

## 建議公開

- World IR 規格；
- 基礎世界編譯器；
- 世界驗證器；
- MUD Runtime Adapter；
- 基礎 Web Client；
- 範例世界；
- Patch 格式；
- 測試框架；
- Provider 介面。

## 可暫不公開

- 高階 Agent 編排；
- 自動程式修正閉環；
- 商業模型路由；
- 大型語義索引；
- 世界品質評分；
- 內部風險控制；
- 大規模 AI 玩家叢集；
- 世界自演化核心。

這可以讓社群建立相容世界與工具，同時保留公司的核心競爭力。

---

# 十六、主要風險

## 16.1 世界一致性崩潰

AI 不斷擴張世界後，可能出現：

- 設定互相矛盾；
- 角色死亡後重新出現；
- 地理位置衝突；
- 規則失效；
- 任務依賴斷裂。

對策：

- 世界公理；
- 關係圖；
- Patch；
- 依賴驗證；
- 自動回歸測試；
- 版本回滾。

---

## 16.2 AI 成本失控

如果每個房間、NPC、玩家動作都呼叫高階模型，成本將快速失控。

對策：

- 生成期集中呼叫；
- 執行期盡量使用確定性規則；
- 低風險任務使用小模型；
- 快取；
- 批次生成；
- 配額；
- 世界級成本預算；
- 玩家級成本限制。

---

## 16.3 AI 自我驗證

同一 Agent 提出修改、執行修改並宣稱成功，會形成虛假的閉環。

對策：

- 角色分離；
- 權限分離；
- 獨立測試；
- 確定性檢查；
- 審查 Agent；
- 人工批准高風險修改。

---

## 16.4 過早追求完全動態世界

完全動態 NPC、即時世界重寫、AI 玩家社會與自動程式修改都具有吸引力，但若過早加入，系統將難以穩定。

第一階段真正需要驗證的是：

> 使用者能否從一份小說或世界觀設定，穩定生成一個可遊玩的文字世界？

只要這一步成立，後續功能才有可靠基礎。

---

# 十七、理論延伸：世界作為持續編譯過程

傳統遊戲開發將世界視為開發完成後被玩家使用的產品。

本架構則將世界視為持續編譯的狀態。

$$
W_{t+1}
=
\mathcal{C}
\left(
W_t,
I_t,
O_t,
P_t,
V_t
\right)
$$

其中：

- $W_t$：時間 $t$ 的世界；
- $I_t$：玩家與創作者輸入；
- $O_t$：世界觀測結果；
- $P_t$：候選修改；
- $V_t$：驗證結果；
- $\mathcal{C}$：受控世界編譯函數。

這意味著世界不再只是被設計，而是在被遊玩、被觀測、被測試與被修正的過程中逐漸形成。

AI 玩家也不只是測試工具，而是世界形成過程中的觀測者。

AI 程式設計者也不只是程式碼生成器，而是世界編譯系統的修復者。

GM Agent 也不只是即興說故事，而是受世界公理、規則、版本與權限限制的動態內容管理者。

---

# 十八、結論

本文提出一個以 MUD 為首個執行介面的 AI 可編譯世界架構。

其核心不是讓 AI 無限制控制遊戲，而是建立以下完整鏈條：

```text
自然語言來源
→ 世界理解
→ 世界中間表示
→ 結構驗證
→ 規則驗證
→ 世界編譯
→ 遊戲執行
→ AI 玩家測試
→ Patch 提案
→ 回歸驗證
→ 版本化部署
```

此架構的關鍵原則是：

1. AI 不直接等於遊戲核心；
2. 世界資料與執行邏輯分離；
3. 所有修改皆以 Patch 形式存在；
4. AI 角色必須分權；
5. 世界、規則、存檔與引擎分別版本化；
6. Snapshot 與事件日誌並存；
7. AI 玩家負責測試，不直接修改正式環境；
8. 高風險程式與世界變更必須經過審查；
9. MUD 是第一個 Runtime，而不是最終限制；
10. 世界本身是一個持續被編譯的動態存在。

最終，本計畫可以發展為：

> 一套讓人類與 AI 共同創造、編譯、測試、運行與演化數位世界的基礎平台。

其真正價值不只在於自動生成遊戲，而在於建立一種新的世界工程方法：

> 世界不是一次被寫完，而是在結構、規則、遊玩、觀測與修正之間持續生成。

---

# 附錄 A：最小 World IR 範例

```yaml
world:
  id: world_001
  title: 黑潮之城
  version: 0.1.0
  status: draft

axioms:
  - id: axiom_001
    description: 魔法必須消耗記憶
    enforcement: hard

regions:
  - id: region_capital
    name: 灰冠城

rooms:
  - id: room_gate
    name: 灰冠城南門
    region: region_capital
    exits:
      north: room_market

characters:
  - id: npc_guard_001
    name: 沉默守衛
    location: room_gate
    behavior: finite_state

rules:
  - id: rule_memory_magic
    trigger: cast_spell
    condition:
      spell_school: memory
    effect:
      memory_points: -3

quests:
  - id: quest_001
    title: 黑潮前兆
    start_npc: npc_guard_001
    states:
      - unavailable
      - available
      - accepted
      - completed
      - failed
```

---

# 附錄 B：世界 Patch 範例

```json
{
  "patch_id": "patch_0001",
  "base_world_version": "0.1.0",
  "target_world_version": "0.1.1",
  "author_role": "world_builder_agent",
  "risk_level": 1,
  "reason": "新增新手任務區域",
  "operations": [
    {
      "op": "add",
      "path": "/regions/training_ground",
      "value": {
        "name": "舊城訓練場"
      }
    }
  ],
  "validation": {
    "schema": "passed",
    "rule_check": "passed",
    "map_reachability": "passed",
    "quest_dependency": "passed"
  }
}
```

---

# 附錄 C：自動測試報告範例

```yaml
test_run:
  id: test_2026_001
  world_version: 0.1.1
  agents:
    - beginner_player
    - explorer_player
    - exploit_player

metrics:
  room_coverage: 0.82
  quest_coverage: 0.74
  branch_coverage: 0.61
  fatal_errors: 0
  soft_locks: 2
  unreachable_rooms: 1
  infinite_resource_loops: 0

issues:
  - id: issue_001
    type: soft_lock
    location: abandoned_mine
    severity: medium
    description: 玩家丟棄鑰匙後無法離開礦坑
```
