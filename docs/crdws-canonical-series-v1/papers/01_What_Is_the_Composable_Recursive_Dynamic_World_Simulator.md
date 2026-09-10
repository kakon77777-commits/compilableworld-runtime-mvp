# Paper 01 — What Is the Composable Recursive Dynamic World Simulator?

**系列：Dynamic World Simulator Canonical Series v1**  
**文件定位：概念憲法 / Canonical Conceptual Constitution**  
**狀態：Canonical Baseline**  
**版本：v1.0**  
**日期：2026-09-10**

---

## 摘要

本文件重新定義原先以「Dynamic World State Machine（動態世界狀態機）」描述的研究與工程目標。

新版目標不再只是建立一個能讓 NPC、國家、經濟或事件持續變化的遊戲狀態機，而是建立一個可以承載**完整世界組合、跨域因果、多時間尺度演化、結構增生、動態分類與動態模擬解析度**的世界模擬基礎。

本系列將其暫定義為：

\[
\boxed{Composable\ Recursive\ Dynamic\ World\ Simulator}
\]

亦可簡稱：

\[
\boxed{CRDWS}
\]

其核心主張是：

> **世界不是一個巨大的單體狀態機，而是大量可獨立描述、可組合、可遞歸分解、可在不同時間尺度運行、可彼此因果耦合的動態系統之集合。**

因此：

\[
\boxed{World=RecursiveCompositionOfDynamicDomains}
\]

而世界的演化不只包括狀態值變動：

\[
StateEvolution
\]

還包括世界結構本身的增生、消失、重組與重新分類：

\[
StructureEvolution
\]

最終：

\[
\boxed{WorldEvolution=StateEvolution+StructureEvolution}
\]

這個定義將成為本系列後續 MSSPXRDRXUNP、UNPNP2、FDCS、TMS、Runtime、CompilableWorld、AI World Assembly 等架構與專案之共同上層基準。

---

# 1. 問題不是「世界會不會動」，而是「什麼叫做一個世界」

傳統遊戲中的世界通常可以被簡化成：

\[
W_t=\{PlayerState,NPCState,QuestState,MapState,InventoryState,\dots\}
\]

接著每一個 tick 或 event 使其變成：

\[
W_t\rightarrow W_{t+1}
\]

這個模型本身沒有錯。

真正的問題是：當目標從一款遊戲，擴大成「動態世界模擬」時，單一 World State 很快就會失去足夠的結構表達能力。

因為一個較完整的世界至少可能同時具有：

- 經濟；
- 軍事；
- 政治；
- 法律；
- 外交；
- 文化；
- 宗教；
- 科學；
- 技術；
- 教育；
- 人口；
- 家庭；
- 人際；
- 組織；
- 企業；
- 生態；
- 氣候；
- 地理；
- 物流；
- 資訊；
- 媒體；
- 犯罪；
- 醫療；
- 建築；
- 生產；
- 能源；
- 交通；
- 以及目前尚未被預先列出的其他系統。

因此問題不應再寫成：

> 「我要替世界增加一個經濟系統。」

真正的問題是：

> **這個世界的架構，是否從一開始就容許任何新的 World Domain 被發現、細分、組合、載入、運算與連接？**

也就是：

\[
\boxed{WorldDomainSet\neq ClosedEnum}
\]

世界不是先寫死十二個系統，再逐年補到二十個、三十個。

世界應該從一開始就接受：

\[
Domain_{new}
\]

作為合法操作。

---

# 2. 從 Dynamic World State Machine 到 Composable World

舊的「Dynamic World State Machine」概念仍然保留價值。

它強調：

- 世界狀態不是靜態資料；
- 世界會自行演化；
- 狀態轉移不必只由玩家觸發；
- NPC、組織、國家、制度與環境可以持續運行；
- 世界在玩家沒有觀察時仍然可以發生事件。

但新版必須再向前一步。

如果把整個世界視為一個巨大 state machine：

\[
W_{t+1}=F(W_t,E_t)
\]

那麼隨著世界擴大，\(F\) 會逐漸成為：

- 無法局部理解；
- 無法局部替換；
- 無法局部驗證；
- 無法調整時間尺度；
- 無法改變模擬解析度；
- 無法讓 AI 安全生成新的功能模組；
- 無法明確表示某一領域的讀寫權限；
- 無法清楚處理跨域因果。

因此新版的基本形式改成：

\[
W_t=\mathcal{C}(D_1(t),D_2(t),\dots,D_n(t))
\]

其中 \(D_i\) 不是固定欄位，而是一個 World Domain。

例如：

\[
D_1=Economy,\quad D_2=Politics,\quad D_3=Military,\quad D_4=Culture
\]

而每一個 Domain 本身又可以繼續組合：

\[
D_i=\mathcal{C}(S_{i1},S_{i2},\dots,S_{im})
\]

例如：

\[
Economy=\{Market,Production,Labor,Finance,Trade,Consumption,Tax,Credit,SupplyChain,\dots\}
\]

而 Subsystem 又能再繼續分解。

因此：

\[
\boxed{World=RecursiveComposition(RecursiveComposition(\dots))}
\]

這就是「Composable」與「Recursive」第一次成為世界模擬的核心本體，而不是附加工程技巧。

---

# 3. Domain 不是 Module

這是新版必須凍結的一條重要界線。

我們不能把：

\[
Economy
\]

直接等同於：

\[
TMS_{economy}
\]

因為一個完整經濟域不可能永遠只由一個功能模組承擔。

正確關係應該更接近：

\[
World\rightarrow Domain\rightarrow Subsystem\rightarrow CapabilityModule
\]

亦即：

\[
\boxed{Domain\neq TMS}
\]

TMS 是功能能力。

World Domain 是世界中的某一類現象空間。

例如「市場」可能需要：

- 交易；
- 定價；
- 供需；
- 庫存；
- 流動性；
- 信用；
- 合約；
- 風險；
- 運輸；
- 稅制；
- 生產。

這些能力可以由多個 TMS 組合。

同一個 TMS 也未必永遠只服務單一 Domain。

因此應將 Domain 視為世界分類與模擬空間，將 TMS 視為可以被載入、組合、替換與驗證的執行能力。

TMS 的正式 contract 留至 Paper 05 定義。

---

# 4. 世界不只會「變」，世界還會「長」

如果世界只有 State Evolution，那麼世界再複雜，本質上仍只是：

\[
ExistingStructure\rightarrow DifferentValues
\]

例如：

- 國庫從 1000 變 800；
- 某人好感從 10 變 20；
- 城市人口從 50,000 變 48,000；
- 戰爭狀態從 false 變 true。

這些都是必要的。

但真正動態世界還必須允許：

\[
ExistingStructure\rightarrow NewStructure
\]

例如一個原本不存在核科技的世界，在科學進展之後可能產生：

\[
science.nuclear\_physics
\]

接著出現：

\[
technology.nuclear\_engineering
\]

再出現：

\[
military.nuclear\_weapons
\]

然後衍生：

\[
politics.nuclear\_deterrence
\]

與：

\[
diplomacy.nonproliferation
\]

這不是「把 nuclear_level 從 0 改成 1」。

這是世界分類空間與系統拓撲本身產生新的節點與關係。

因此新版的核心要求是：

\[
\boxed{WorldEvolution=StateEvolution+StructureEvolution}
\]

Structure Evolution 可以包括：

- 新 Entity 出現；
- 新 Entity 類型出現；
- 新 Relation 類型出現；
- 新 Domain 出現；
- 新 Subsystem 出現；
- 新 TMS 被載入；
- 舊 TMS 被替換；
- 新因果連線建立；
- 新制度形成；
- 舊制度崩解；
- 世界分類深度增加；
- 世界分類深度降低；
- 模擬 topology 重組。

這使「世界」從一個資料集合，升級成一個會改變自身可表達結構的動態系統。

---

# 5. 世界的完整存在，不等於完整計算

如果世界允許無限制遞歸分類，那馬上會出現一個現實問題：

\[
Computation\rightarrow Explosion
\]

我們不可能在任何時刻，對所有經濟、軍事、政治、文化、人際、科學、技術、生態、醫療、教育等領域，都使用最高解析度持續模擬。

因此必須凍結另一條核心原則：

\[
\boxed{FullExistence\neq FullResolution}
\]

一個 World Domain 可以存在，但不代表它現在需要被完整展開。

例如玩家正在一座邊境城市，此時可能需要：

- 玩家周邊人際關係：高解析；
- 城市物流：高解析；
- 當地治安：中高解析；
- 國家經濟：中解析；
- 遠方城市居民日常：低解析；
- 另一大陸的地方學校課表：極低解析；
- 遙遠研究機構的內部個人關係：必要時才展開。

因此世界應該允許：

\[
Resolution(D_i,t)
\]

成為動態量。

它可以受到：

\[
CausalRelevance,Observation,Activity,Risk,Importance,DependencyDepth
\]

等因素影響。

此處將與新版 FDCS、UNPNP2 直接相接。

其正式解析度模型留至 Paper 04。

---

# 6. 分類深度本身必須是動態的

傳統 taxonomy 常假設：

```text
World
└─ Economy
   ├─ Market
   ├─ Labor
   └─ Finance
```

這種結構在靜態知識表示上非常方便。

但動態世界不能假設：

> 這就是最終分類。

因為不同世界、不同時代、不同技術水平、不同觀察尺度，都可能需要不同的分類深度。

例如「Science」在低解析度時只是：

```text
Science
```

提高解析度後：

```text
Science
├─ Physics
├─ Chemistry
├─ Biology
├─ Medicine
└─ Computing
```

再提高：

```text
Physics
├─ Mechanics
├─ Thermodynamics
├─ Electromagnetism
├─ Quantum
└─ Nuclear Physics
```

因此：

\[
\boxed{ClassificationDepth=Dynamic}
\]

這也是 UNPNP2 在本世界模擬架構中的重要位置之一：不是替世界建立一棵永遠固定的分類樹，而是容許：

\[
ClassificationExpansion
\]

\[
ClassificationContraction
\]

\[
ClassificationRecomposition
\]

成為 Runtime／模擬治理的一部分。

但 UNPNP2 的精確形式、路徑表示與分類運算，不在 Paper 01 預先封死。

Paper 01 只凍結需求：

> **世界的分類邊界與分類深度不能被假設為永久固定。**

---

# 7. 世界不是單一 tick

另一個傳統世界模擬容易遇到的問題，是把所有系統綁進同一個全域 tick：

```text
tick economy
tick politics
tick military
tick culture
tick science
tick relationships
...
```

這會讓完全不同時間尺度的系統被迫同步。

但現實世界中：

\[
\tau_{combat}\neq\tau_{conversation}\neq\tau_{market}\neq\tau_{politics}\neq\tau_{culture}\neq\tau_{demography}
\]

因此新版必須採用：

\[
\boxed{MultiRateWorldSimulation}
\]

例如：

- 戰鬥：毫秒／秒；
- 對話：秒／分鐘；
- 交易：秒／日；
- 物流：小時／週；
- 生產：小時／月；
- 政治：日／年；
- 科學研究：月／十年；
- 文化：月／世代；
- 人口：年／世紀。

有些系統適合 TickDriven，有些適合 EventDriven，有些適合 DeferredReconstruction，有些只需要 SummaryState。

因此世界 Runtime 的責任，不是替所有系統提供相同更新頻率，而是維持不同時間尺度之間的正確因果與狀態一致性。

---

# 8. 世界真正困難的地方是 Cross-Domain Causality

如果只把經濟、軍事、政治、文化各自做成獨立模組，仍然不算完整世界。

因為真正的世界不是：

\[
Economy+Politics+Military+Culture
\]

而是：

\[
Economy\leftrightarrow Politics\leftrightarrow Military\leftrightarrow Culture\leftrightarrow Science\leftrightarrow Interpersonal\leftrightarrow\dots
\]

例如：

\[
War\rightarrow LogisticsDemand\rightarrow IndustrialExpansion\rightarrow LaborShortage\rightarrow WageChange\rightarrow Migration\rightarrow PoliticalPressure
\]

或：

\[
ScientificDiscovery\rightarrow NewTechnology\rightarrow NewIndustry\rightarrow NewClassStructure\rightarrow CulturalChange
\]

因此世界需要的不只是 module interface，而是可追蹤的：

\[
\boxed{CrossDomainCausalGraph}
\]

這些因果關係不一定全部是固定規則。

有些可以來自：

- 明確 operator；
- 統計模型；
- 規則系統；
- Agent 決策；
- AI 推演；
- 歷史狀態；
- 外部事件；
- 隨機擾動；
- 使用者操作。

因此世界模擬器必須允許多種因果來源共存，但不能因此失去 authority 與 provenance。

---

# 9. Game 不是 World

這是本系列另一條重要凍結原則：

\[
\boxed{World\neq Presentation}
\]

一個世界 \(W_t\) 可以被投影成：

- 3D RPG；
- Strategy Map；
- Grand Strategy；
- Text Adventure；
- Management UI；
- Debugger；
- AI Agent Observation；
- Research Simulation；
- Replay；
- Visualization Dashboard。

因此：

\[
World\rightarrow Projection\rightarrow Experience
\]

而不是：

\[
GameScene=World
\]

這意味著：

- Renderer 不擁有世界真相；
- UI 不應偷偷實作世界規則；
- Presentation object identity 不等於 World Entity identity；
- World 可以在無視覺 Presentation 時繼續存在；
- 同一世界可以同時有多個 Presentation。

這個原則已經能與現有 CompilableWorld / AI World Assembly / Three.js 的工程線自然對接，但 Paper 01 不把那些專案直接等同於本世界模擬器。

它們是可重用工程基礎或相鄰系統，不是概念本體的全部。

---

# 10. AI 可以建世界，但 AI 不能自動成為世界真理

未來這套系統必然高度依賴 AI。

AI 可以：

\[
Generate,Assemble,Search,Classify,Validate,Repair,Simulate,ProposeNewDomain,ProposeNewTMS
\]

但仍需保留：

\[
\boxed{AI\neq WorldAuthority}
\]

否則 GeneratedPossibility 會被錯誤提升成 CanonicalWorldTruth。

因此需要區分：

\[
Proposal
\]

\[
Validation
\]

\[
PromotionReadiness
\]

\[
PromotionAuthority
\]

\[
Canonicalization
\]

這些不是同一件事。

未來即使 AI 能自動發現世界缺少某個金融、宗教、軍事或醫療子系統，它也應該先：

\[
MissingCapability\rightarrow Search\rightarrow Reuse\rightarrow Compose\rightarrow GenerateCandidate\rightarrow Validate
\]

而不是直接：

\[
Generate\rightarrow Canonical
\]

這條治理原則將與現有 AI World Assembly 系列接軌。

---

# 11. 這個系統不是什麼

為避免未來專案混淆，本文件先凍結以下負面定義。

## 11.1 它不是單一遊戲引擎

Unity、Unreal、Godot、Three.js 等可以作為 Presentation 或執行環境的一部分，但不等於本系統。

## 11.2 它不是單一 ECS

Entity Component System 可以成為某些 Runtime 實作方式，但 CRDWS 的問題範圍比 ECS 更高層。

## 11.3 它不是單一 Agent Simulation

NPC Agent 可以是世界的一部分，但世界還包含制度、價格、物流、自然環境、科學、歷史與其他非人格系統。

## 11.4 它不是單一知識圖譜

知識圖譜可以描述 Entity 與 Relation，但本系統還必須處理時間、狀態演化、因果、模組能力與 simulation resolution。

## 11.5 它不是 AI World Assembly

AI World Assembly 處理的是組裝、候選、驗證、修復與治理。

CRDWS 是世界本身如何被組成與持續演化的更高層問題。

兩者可以深度耦合，但不能同名化。

## 11.6 它不是 CompilableWorld

CompilableWorld 是目前重要的 executable world-state Runtime / authoring / compile 基礎之一。

但 CRDWS 的完整目標還包含 recursive domain composition、dynamic resolution、multi-rate simulation、cross-domain causality、structure evolution 等更廣範圍。

## 11.7 它不是固定世界 ontology

任何目前列出的 Domain 都只是當前已知集合，不代表最終集合。

---

# 12. Canonical Invariants v1

以下原則在本系列目前時空階段視為 Frozen Invariants。

除非未來出現結構性反例，否則不因局部實作便利而修改。

## Invariant 1 — World Is Recursive Composition

\[
\boxed{World=RecursiveCompositionOfDynamicDomains}
\]

## Invariant 2 — Domain Set Is Open

\[
\boxed{DomainSet\neq ClosedEnum}
\]

## Invariant 3 — Domain Is Not Capability Module

\[
\boxed{Domain\neq TMS}
\]

## Invariant 4 — World Evolution Has Two Dimensions

\[
\boxed{WorldEvolution=StateEvolution+StructureEvolution}
\]

## Invariant 5 — Full Existence Does Not Require Full Resolution

\[
\boxed{FullExistence\neq FullResolution}
\]

## Invariant 6 — Classification Depth Is Dynamic

\[
\boxed{ClassificationDepth=Dynamic}
\]

## Invariant 7 — Simulation Time Is Multi-Rate

\[
\boxed{WorldTime\neq SingleGlobalTick}
\]

## Invariant 8 — Cross-Domain Causality Is First-Class

\[
\boxed{DomainInteraction\neq Afterthought}
\]

## Invariant 9 — World Is Not Presentation

\[
\boxed{World\neq Presentation}
\]

## Invariant 10 — AI Is Not Automatic World Authority

\[
\boxed{AI\neq CanonicalWorldAuthority}
\]

## Invariant 11 — Search and Reuse Before New Capability Generation

\[
\boxed{MissingCapability\rightarrow Search\rightarrow Reuse/Compose\rightarrow GenerateCandidate}
\]

## Invariant 12 — Composition Must Remain Inspectable

\[
\boxed{Composable\Rightarrow Traceable}
\]

任何 World Domain、Subsystem、TMS、State、Event、Operator 或因果連線，都應盡可能能追蹤其來源、版本、讀寫範圍與證據。

---

# 13. 本系列目前的概念總圖

目前可以用下式描述：

\[
\boxed{WorldIntent\rightarrow ClassificationSpace\rightarrow DomainComposition\rightarrow TMSCapabilityComposition\rightarrow WorldStateSpace\rightarrow Causal/TemporalSimulation\rightarrow DynamicResolution\rightarrow Projection\rightarrow Observation\rightarrow WorldEvolution}
\]

而其中 World Evolution 又回饋：

\[
WorldEvolution\rightarrow ClassificationExpansion
\]

\[
WorldEvolution\rightarrow TMSRecomposition
\]

\[
WorldEvolution\rightarrow NewWorldStructure
\]

因此不是線性 pipeline，而是遞歸閉環：

\[
\boxed{World\rightarrow Simulation\rightarrow Observation\rightarrow Recomposition\rightarrow World'}
\]

---

# 14. 與 MSSPXRDRXUNP / UNPNP2 / FDCS / TMS 的關係

Paper 01 不提前凍結這些系統的全部細節。

目前只確立其高層位置。

### MSSPXRDRXUNP / UNPNP2

負責支持：

- 不預設最終分類深度；
- 路徑與結構的遞歸展開；
- 動態世界結構組合；
- 未知 Domain / Subsystem 的新增空間。

### FDCS

負責支持：

- 分類解析度；
- 模擬解析度；
- 展開／折疊；
- 高低精度切換；
- 計算成本與因果重要性的動態治理。

### TMS

負責支持：

- 真正可執行的世界能力；
- 可載入；
- 可替換；
- 可驗證；
- 可組合；
- 可限制讀寫權限。

### Runtime

負責：

- 狀態；
- 時間；
- 事件；
- 因果；
- transaction；
- world structure evolution；
- multi-rate execution。

其正式責任邊界由後續文件定義。

---

# 15. 目前時空階段的 Frozen Baseline

本文件不是宣稱「世界模擬問題已經完成」。

它凍結的是：

> **我們現在已經知道，未來不應該再把這個專案降回一個單體動態狀態機、固定 Domain 枚舉、固定 tick、固定分類樹或遊戲 UI 主導的世界系統。**

也就是：

\[
\boxed{NoReturnToMonolithicWorldStateMachine}
\]

後續實作可以變。

TMS contract 可以升版。

FDCS algorithm 可以改。

UNPNP2 的數學表示可以改。

Runtime 可以重新設計。

資料庫可以替換。

Presentation 可以新增。

但只要沒有新的結構性反例，本文件的上層世界觀保持不變：

\[
\boxed{World=Open+Composable+Recursive+Dynamic+MultiRate+Causal+ResolutionAdaptive}
\]

---

# 16. 本系列後續文件

本系列後續 canonical 文件規劃如下：

1. **What Is the Composable Recursive Dynamic World Simulator**
2. **MSSPXRDRXUNP / UNPNP2 Canonical Architecture**
3. **World Domain Recursive Composition**
4. **FDCS / UNPNP2 Dynamic Simulation Resolution**
5. **TMS World Capability Module Specification**
6. **Project Lineage, Locator and Non-Confusion Map**
7. **Current Implementation Baseline and Migration Plan**
8. **Frozen Invariants and Future Roadmap**

Paper 01 負責「世界是什麼」。

Paper 02–05 負責「它如何被建成」。

Paper 06 負責「哪些專案是什麼，不能混淆什麼」。

Paper 07 負責「現有專案怎麼遷移」。

Paper 08 負責「哪些東西在目前時空階段先凍結，以及未來往哪裡走」。

---

# 結論

新版 Dynamic World Simulator 的核心，不是讓更多變數每秒更新。

它真正的目標是建立一種足以承載「世界」的計算結構。

這個世界可以：

- 擁有未知數量的 Domain；
- 將 Domain 遞歸分解；
- 將功能能力以 TMS 組合；
- 在不同時間尺度運行；
- 根據因果與觀察動態改變解析度；
- 讓不同 Domain 互相影響；
- 讓世界結構本身成長；
- 被多種 Presentation 投影；
- 讓 AI 搜尋、組合、生成與修復；
- 但仍保留明確的 authority 與 canonicalization 邊界。

因此本系列目前採用的最高層定義為：

\[
\boxed{Composable\ Recursive\ Dynamic\ World\ Simulator}
\]

以及其核心命題：

\[
\boxed{A\ World\ Is\ A\ Recursive\ Composition\ Of\ Dynamical\ Systems}
\]

而真正的動態世界，不只是「世界裡的數值會變」。

真正的動態世界是：

\[
\boxed{The\ World\ Can\ Change\ What\ The\ World\ Is}
\]

---

**End of Paper 01**
