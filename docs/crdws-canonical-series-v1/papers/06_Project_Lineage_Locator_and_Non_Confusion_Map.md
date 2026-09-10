# Paper 06 — Project Lineage, Locator and Non-Confusion Map

**系列：Dynamic World Simulator Canonical Series v1**  
**文件定位：Project Lineage / Search Locator / Non-Confusion Canonical Map**  
**狀態：Canonical Baseline**  
**版本：v1.0**  
**日期：2026-09-10**

---

## 摘要

前五篇已經建立新版 Dynamic World Simulator 的核心架構：

\[
\boxed{
Composable\ Recursive\ Dynamic\ World\ Simulator
}
\]

並逐步區分：

- World；
- Domain；
- Subsystem；
- UNPNP2；
- FDCS；
- MSSP；
- XRDR；
- TMS；
- World Runtime；
- Projection；
- AI World Assembly；
- Semantic Authority。

但 Neo.K 過去已經建立大量理論、白皮書、Runtime、MVP、實驗工作區與相鄰專案。

如果沒有一份明確的 Project Lineage / Locator Map，未來的人類或 AI 很容易犯下以下錯誤：

- 看到 `MSSP` 就認為所有 MSSP 專案都是同一個系統；
- 看到 `runtime` 就認為它是 Dynamic World Simulator；
- 把 `mssp-game-computer-runtime-mvp` 誤認為世界模擬 Runtime；
- 把 `AI World Assembly` 當成 World Runtime；
- 把 `SEDB` 當成世界狀態資料庫；
- 把 `RDSS` 當成 MSSPXRDRXUNP 的新名字；
- 把 `CompilableWorld` 當成完整 CRDWS；
- 把 `FDCS` 當成普通 LOD；
- 把 `UNPNP2` 當成 Runtime engine；
- 把歷史文件中的舊架構角色直接覆寫成新版定義；
- 在找不到 repo 時自行猜一個 repo 名稱。

因此本文件建立：

\[
\boxed{
ProjectLineage
+
Locator
+
NonConfusionMap
}
\]

其首要原則為：

\[
\boxed{
Related
\neq
Identical
}
\]

以及：

\[
\boxed{
Successor
\neq
RetroactiveRewriteOfPredecessor
}
\]

本文件不刪除舊概念。

舊文件仍然是研究歷史與 provenance。

但從本系列 v1 開始，未來若要實作新版 Dynamic World Simulator，應優先以本系列 Paper 01–08 作為新的 architecture baseline，再回頭從舊專案抽取可保留能力。

---

# 1. 這篇文件的用途

未來任何 AI 或人類遇到以下問題時，先讀 Paper 06：

> 「MSSP 到底在哪？」

> 「MSSP×RDR 跟 MSSPXRDRXUNP 是不是一樣？」

> 「原本的 world runtime 是哪個 repo？」

> 「CompilableWorld 和 Dynamic World Simulator 是不是同一個專案？」

> 「AI World Assembly 是不是新世界引擎？」

> 「SEDB 應不應該直接存 Runtime mutable state？」

> 「RDSS 是不是取代 MSSP？」

> 「FDCS 到底要去哪裡找？」

> 「UNPNP2 有沒有 GitHub repo？」

> 「那個名字裡有 `game-computer-runtime` 的是不是我們要的動態世界專案？」

Paper 06 的責任不是解釋每個理論全部內容。

它負責：

\[
\boxed{
FindTheRightSourceBeforeReasoning
}
\]

---

# 2. Canonical Source Priority

從 2026-09-10 起，針對新版 Dynamic World Simulator，建議使用以下 source priority：

```text
Priority 0
Dynamic World Simulator Canonical Series v1
Paper 01–08

Priority 1
Current executable engineering repositories
例如 compilableworld-runtime-mvp / ai-world-assembly / SEDB

Priority 2
Current/late historical technical whitepapers
例如 MSSP_RDR_RUNTIME_ARCHITECTURE / FDCS 2.0 / Dynamic MSSP

Priority 3
Older prototypes / superseded implementations
例如 CompilableWorld-Evennia-Prototype

Priority 4
Adjacent theories / experiments / field labs
例如 RDSS operatorization、MSSP_Board probes、AI attention substrate 等
```

但 priority 不代表：

\[
NewerSource
\Rightarrow
OldSourceInvalid
\]

而是：

\[
NewerCanonicalArchitecture
\Rightarrow
CurrentImplementationDecisionPriority
\]

舊資料仍用來：

- 找概念祖先；
- 理解設計原因；
- 找舊演算法；
- 比較演化；
- 抽取可重用 module；
- 檢查是否重複發明。

---

# 3. 新的最高層 Canonical Target

本系列目前將最高層目標定義為：

\[
\boxed{
Composable\ Recursive\ Dynamic\ World\ Simulator
}
\]

暫稱：

\[
CRDWS
\]

這個名稱描述的是**新 canonical architecture target**。

它不是目前某一個 GitHub repo 的既有正式名稱。

因此：

\[
\boxed{
CRDWS
\neq
RepositoryName
}
\]

在完成 Paper 07 migration audit 前，不應先假設：

```text
某一個舊 repo = 完整 CRDWS
```

正確做法是：

\[
ExistingProjects
\rightarrow
MigrationAudit
\rightarrow
Keep/Adapt/Replace
\rightarrow
CRDWSImplementation
\]

---

# 4. 第一條最重要 Non-Confusion Rule

## 4.1 `compilableworld-runtime-mvp`

**Verified GitHub anchor**

```text
kakon77777-commits/compilableworld-runtime-mvp
```

Drive 中另有 project locator：

```text
project-mssp-world-runtime.md
```

該 project locator 將 `compilableworld-runtime-mvp` 描述為：

> successor to CompilableWorld-Evennia-Prototype

並標記為 Neo.K MUD / world-engine work 的 main line。

GitHub README 則明確描述：

\[
AuthoringLayer
\rightarrow
RuntimePackage
\rightarrow
MSSPModularWorldKernel
\]

且 Terminal / Web 介面共用：

- Kernel；
- Action IR；
- Module Contract；
- Runtime state/action/event pipeline。

因此在目前已確認的工程資產中：

\[
\boxed{
compilableworld-runtime-mvp
=
CurrentExecutableWorldRuntimeAnchor
}
\]

但仍要注意：

\[
\boxed{
CompilableWorld
\neq
CompleteCRDWS
}
\]

它是最重要 Runtime 基礎之一，

不是 Paper 01–05 所定義全部世界模擬能力的完成體。

---

# 5. 第二條最重要 Non-Confusion Rule

## 5.1 `mssp-game-computer-runtime-mvp`

**Verified GitHub anchor**

```text
kakon77777-commits/mssp-game-computer-runtime-mvp
```

這個 repo 名稱非常危險。

因為它同時包含：

- MSSP；
- Game；
- Computer；
- Runtime。

未來 AI 很容易誤判：

> 「這應該就是 MSSP 動態世界 Runtime。」

這是錯的。

其 README 明確定義：

> 以 MSSP × RDR 重寫的 Windows 遊戲限定、最小權限、可審計 Computer Use MCP。

它的核心功能是：

- window selection；
- screenshot；
- keyboard / mouse；
- visual diff；
- continuous vision；
- multimodal lease；
- live control plane；
- action verification；
- audit；
- provider foundation。

其 MSSP mapping 中：

```text
TMS = reserved
```

用途是：

> 遊戲校準與語義技能

而不是 Dynamic World Simulation Domain TMS。

因此必須凍結：

\[
\boxed{
mssp\text{-}game\text{-}computer\text{-}runtime
\neq
DynamicWorldRuntime
}
\]

它是：

\[
\boxed{
AIComputerUseRuntimeForGames
}
\]

兩者未來可以互相使用，

例如 AI 透過 Computer Use 操作某個遊戲世界，

但不能把架構本體混在一起。

---

# 6. `CompilableWorld-Evennia-Prototype`

**Verified GitHub anchor**

```text
kakon77777-commits/CompilableWorld-Evennia-Prototype
```

Drive project locator：

```text
project-mud-world-engineering.md
```

已明確標記：

```text
SUPERSEDED 2026-07-13
```

其 successor 是：

```text
compilableworld-runtime-mvp
```

因此：

\[
\boxed{
EvenniaPrototype
=
HistoricalReference
}
\]

而不是目前 world-engine mainline。

正確使用方式：

- 比較舊設計；
- 找 compatibility idea；
- 找歷史 prototype；
- 考古某些早期 world authoring 決策。

不應：

- 在新版 CRDWS 上繼續以 Evennia-specific constraint 當最高層架構；
- 因 prototype 先有某種 object model，就假設世界只能那樣表示。

---

# 7. `mssp-core`

**Verified GitHub anchor**

```text
kakon77777-commits/mssp-core
```

目前 main README 很短：

```text
MSSP Core
Bootstrap commit.
```

並指出完整 MSSP Core MVP 曾透過 dedicated branch / draft PR 提出。

因此：

\[
\boxed{
mssp\text{-}core
=
MSSPCoreRepositoryAnchor
}
\]

但不能因 repo 名叫 `mssp-core` 就假設 main branch 已完整承載所有歷史 MSSP 理論與最新 MSSPXRDRXUNP。

查 MSSP 理論時仍需同時查 Drive / website technical whitepapers。

---

# 8. `MSSP_Board`

**Verified GitHub anchor**

```text
kakon77777-commits/MSSP_Board
```

它不是 Runtime mainline。

README 定義它為：

> 三個 AI 的實作工作區。

用途是：

- probes；
- discussion；
- attacks；
- mutation；
- executable claims；
- field-lab validation。

而且 README 明確說：

> `probes/` 是蒸餾，不是複本。

若 probe 與網站條目不一致，

應回 MSSP 網站上可執行版本查證。

因此：

\[
\boxed{
MSSPBoard
=
ExperimentalFieldLab
}
\]

不是：

\[
MSSPBoard
=
CanonicalMSSPRuntime
\]

---

# 9. MSSP public documentation anchor

`MSSP_Board` README 指向：

```text
thisoneisneok.com/mssp
```

以及 development / log pages。

因此搜尋 MSSP 時的順序不應只有 GitHub repo search。

建議：

```text
1. Dynamic World Simulator Canonical Series
2. MSSP website / technical whitepapers
3. mssp-core
4. MSSP_Board field lab
5. related runtime repos
```

---

# 10. MSSP historical Drive locator

已確認 Google Drive 有大量 MSSP 文件。

高價值入口包括：

```text
MSSP-0.1-to-1.0-Technical-Whitepaper.zh-TW.md
```

以及：

```text
11_從靜態MSSP到動態MSSP_讓架構角色成為可觀察狀態.md
```

還有：

```text
02_MSSP_RDR_RUNTIME_ARCHITECTURE.md
```

與：

```text
05_權威結構與執行派發_格子語言CAIR_MSSP與RDR的接合_v0.1.md
```

因此搜尋歷史 MSSP 演化時：

\[
\boxed{
GitHubOnly
=
Insufficient
}
\]

---

# 11. MSSP → Dynamic MSSP → MSSP×RDR → MSSPXRDRXUNP

這些名稱具有 lineage，

但不能直接寫成：

\[
MSSP
=
DynamicMSSP
=
MSSP\times RDR
=
MSSPXRDRXUNP
\]

更正確是：

```text
MSSP
  ↓
Dynamic MSSP
  ↓
MSSP + RDR integration
  ↓
MSSP×RDR / MSSP_RDR Runtime line
  ↓
MSSPXRDRXUNP
  ↓
Current CRDWS canonical interpretation
```

其中每一次演化都可能：

- 保留舊結構；
- 改變責任；
- 抽象化；
- 新增 layer；
- 將某些舊角色重新定位。

因此：

\[
\boxed{
Lineage
\neq
Synonymy
}
\]

---

# 12. RDR / XRDR

歷史文件有：

```text
02_MSSP_RDR_RUNTIME_ARCHITECTURE.md
```

以及 MSSP / RDR 接合文件。

在本系列 Paper 02 中，

XRDR 的 canonical responsibility 被重新整理為：

\[
\boxed{
RecursiveDynamicResolutionDispatchAndRecompositionLayer
}
\]

這是本系列的**現階段架構責任解讀**。

它不應被用來聲稱：

> 所有舊 RDR 文件從一開始就是這個精確定義。

因此：

\[
CurrentCanonicalRole
\neq
HistoricalTerminologyRewrite
\]

---

# 13. TMS

TMS 在不同 MSSP 專案裡可能曾代表不同具體角色或預留位置。

例如：

`mssp-game-computer-runtime-mvp` README 中：

```text
TMS = reserved
```

且用途是遊戲校準與語義技能。

而本系列 Paper 05 已重新凍結 Dynamic World Simulator 中：

\[
\boxed{
TMS
=
ExecutableWorldCapabilityModule
}
\]

因此：

> 找舊 TMS 實作時，不能只搜尋字串 `TMS` 後就假設語義完全相同。

必須先判斷文件所屬 project / date / architecture generation。

---

# 14. `SEDB`

**Verified GitHub anchor**

```text
kakon77777-commits/SEDB
```

README 定義：

```text
Semantic Evolution Database
/
AI-Native Unbounded Dynamic Field System
```

其核心是：

- dynamic fields；
- semantic evolution；
- provenance；
- epistemic status；
- schema expansion；
- merge / split / convergence / reactivation。

因此：

\[
\boxed{
SEDB
=
SemanticAndSchemaEvolutionInfrastructure
}
\]

在 AI World Assembly 中，目前 SEDB 被定位為：

\[
Semantic/ContentTruth
\]

但必須凍結：

\[
\boxed{
SEDB
\neq
WorldRuntimeStateStore
}
\]

至少在目前 architecture 中，

不要把：

- HP；
- combat transient state；
- frame-by-frame NPC position；
- Runtime transaction；

全部直接推進 SEDB 當作世界執行 state。

---

# 15. SEDB 與 UNPNP2 / FDCS 的關係

三者都可能談「動態欄位／分類／展開」。

因此也很容易混淆。

可以先用：

\[
SEDB
\rightarrow
Semantic/SchemaEvolution
\]

\[
UNPNP2
\rightarrow
OpenClassificationAndUnitizationSpace
\]

\[
FDCS
\rightarrow
DynamicResolutionGovernance
\]

區分。

它們可以互相支援，

但不是同義系統。

---

# 16. `ai-world-assembly`

**Verified GitHub anchor**

```text
kakon77777-commits/ai-world-assembly
```

README 第一層就明確寫：

> integration layer, not a replacement for SEDB or CompilableWorld.

其 architecture boundary 為：

```text
SEDB
→ semantic/content truth

CSC-OCM
→ module/capability composition

Dynamic Asset Graph
→ assembly topology

CompilableWorld
→ committed runtime state/action/event authority

Presentation
→ rendering/input/audio/UI

AI World Assembler
→ proposal/planning/generation/validation/repair
```

因此：

\[
\boxed{
AWA
=
AssemblyAndGovernanceLayer
}
\]

而：

\[
\boxed{
AWA
\neq
WorldRuntime
}
\]

也：

\[
\boxed{
AWA
\neq
DynamicWorldSimulator
}
\]

未來 CRDWS 可以把 AWA 當作：

- Missing TMS search/generation；
- Missing Domain artifact generation；
- validation；
- repair；
- candidate assembly；
- multi-world orchestration；

但世界持續運轉仍由 World Runtime 負責。

---

# 17. CompilableWorld 與 AWA

兩者關係可寫成：

\[
AWA
\rightarrow
Assemble/Validate/Repair
\]

\[
CompilableWorld
\rightarrow
Compile/Execute/Commit
\]

因此：

\[
\boxed{
Assembler
\neq
Executor
}
\]

AWA 不應直接偷做 world state commit。

CompilableWorld 也不應自己變成 AI content canonicalizer。

---

# 18. RDSS

GitHub 同名 repo 搜尋目前沒有確認到 public repo。

但 Google Drive 已確認大量 RDSS 文件，例如：

```text
ON_RDSS_Research_Handoff_v1.0.md
RDSS_Operatorization_Translation_Matrix_v0.1.md
Operator_Native_RDSS_Primitive_Algebra_v0.1.md
Operator_Native_RDSS_Deep_Formal_Backbone_v0.2.md
ON_RDSS_Type_and_Effect_Calculus_v0.6.md
...
```

因此：

\[
\boxed{
RDSS
=
VerifiedResearchDocumentLine
}
\]

但：

\[
\boxed{
NoVerifiedSameNameGitHubRepo
}
\]

截至本文件建立時，不應虛構：

```text
kakon77777-commits/RDSS
```

---

# 19. RDSS 不等於 MSSPXRDRXUNP

RDSS 可能和：

- recursive dynamic state；
- operatorization；
- state container；
- type/effect；
- branch/quotient；
- causality；

有深度可接關係。

但必須保留：

\[
\boxed{
RDSS
\neq
MSSPXRDRXUNP
}
\]

較安全的定位是：

\[
RDSS
=
Adjacent/HigherLevelFormalResearchLine
\]

可以提供 CRDWS：

- formal operator；
- state composition；
- type/effect；
- verification；

但不能直接宣稱：

> RDSS 就是新版 Dynamic World Simulator。

除非未來有新 canonical 文件明確合併。

---

# 20. FDCS

GitHub 同名 repo 搜尋目前沒有確認到 public repo。

但 Drive 已確認多條 FDCS 文件：

```text
FDCS_2.0_MWT_Ledger_Native_Revision_Baseline_v0.1_ZH.md
FDCS（分形動態因果系統）化學版.docx
FDCS 2.0終極版：平行剪枝與混合本體論計算(舊).docx
02_HSDM_x_FDCS_x_AI歷史研究Runtime...
AMEP-FDCS-CausalOps-Agent-Execution-v0.1.md
```

因此：

\[
\boxed{
FDCS
=
MajorResearchLineWithDriveCorpus
}
\]

不是目前已確認的 dedicated GitHub repo。

---

# 21. FDCS historical meaning vs current CRDWS role

歷史 FDCS 有「分形動態因果系統」、平行剪枝、混合本體論等研究。

本系列 Paper 04 將它在 CRDWS 中重新定位成：

\[
\boxed{
DynamicClassificationAndSimulationResolutionGovernor
}
\]

這是「把既有 FDCS 能力接到 Dynamic World Simulator」的 architecture role。

不要反向宣稱：

> 所有 FDCS 歷史研究都只是在做 world LOD。

這會錯。

---

# 22. UNP / UNPNP / UNPNP-II / UNPNP2

GitHub 同名 repo 搜尋目前沒有確認到 public repo。

Drive 搜尋已確認：

`Aletheia Conversation Crystals` 與 `Async Open Loops` 內有：

```text
UNPNP-II
```

並以：

- observer；
- chart；
- scale-relative；
- computational unitization；

等語義連結到 One-All / True ETN / Cloud AI Center 等研究線。

因此：

\[
\boxed{
UNPNP2
=
VerifiedCurrentResearchConcept
}
\]

但目前應透過：

- Drive memory/crystals；
- UNPNP-II 關鍵詞；
- One-All；
- observer scale；
- chart-relative center；
- dynamic unitization；

搜尋。

不要自行假設有：

```text
kakon77777-commits/UNPNP2
```

---

# 23. UNPNP2 在本系列中的定位

Paper 02 / 04 目前只凍結：

\[
\boxed{
UNPNP2
=
OpenRecursiveClassificationAndPathSpace
}
\]

以及它對：

\[
DynamicUnitization
\]

與：

\[
NoFinalClassificationDepthAssumption
\]

的支援。

這是 CRDWS integration role。

它不表示 UNPNP2 全部理論等於分類系統。

---

# 24. World State Machine research corpus

如果要找「動態世界狀態機」的概念祖先，

Google Drive 已確認有：

```text
04_從狀態機到世界狀態機_AI為何不應每輪重新理解世界.md
```

```text
02_母AI世界狀態機與子智能網路.md
```

```text
狀態、容器與存在：遞歸動態狀態系統的總命題.md
```

以及：

```text
外部注意力場工程系列_09_計算機宇宙世界狀態注意力管理_v0.1.md
```

因此找 world-state 理論時，

應用：

```text
世界狀態機
動態世界
world state
狀態 容器 存在
母AI世界狀態機
遞歸動態狀態
```

作為第一批 query。

---

# 25. `project-mssp-world-runtime.md`

這是一個非常重要的 Drive project locator。

它直接記錄：

```text
project-mssp-world-runtime
```

description 指向：

```text
compilableworld-runtime-mvp
```

並明確稱其為：

> successor to CompilableWorld-Evennia-Prototype

以及：

> main line of development for Neo's MUD/world-engine work

因此未來若說：

> 「回到原本 MSSP 世界 Runtime。」

優先 locator 應是：

\[
\boxed{
project\text{-}mssp\text{-}world\text{-}runtime
}
\]

然後再落到：

\[
\boxed{
compilableworld\text{-}runtime\text{-}mvp
}
\]

而不是憑 repo 名猜。

---

# 26. 目前「動態世界模擬器」與 CompilableWorld 的關係

新的 CRDWS target 比現有 CompilableWorld 更大。

因此暫定：

\[
\boxed{
CompilableWorld
\subset
FutureCRDWSImplementationStack
}
\]

這裡的 \(\subset\) 是 architecture capability inclusion 的意思，

不是程式碼繼承。

現有 CompilableWorld 已具備重要能力：

- Authoring Layer；
- Runtime Package；
- MSSP module kernel；
- Action IR；
- StateDelta；
- EventIR；
- Entity transaction；
- FunctionIR；
- ScenarioIR；
- State machines；
- module contracts；
- UI-decoupled execution。

但 Paper 01–05 新增的 CRDWS target 還需要：

- open Domain Graph；
- Domain structure evolution；
- UNPNP2 dynamic classification；
- FDCS multi-dimensional resolution；
- multi-rate world simulation；
- resolution-aware TMS selection；
- cross-domain causal graph；
- aggregate ↔ microstate transition；
- structure mutation governance。

所以：

\[
\boxed{
DoNotRewriteCompilableWorldImmediately
}
\]

Paper 07 應先 audit。

---

# 27. Söldnerschild /《傭兵之盾》

本系列前一輪討論曾把它拿來作：

\[
LegacyReconstruction
\rightarrow
DynamicWorldTransformation
\]

類型 benchmark。

但目前這次 GitHub / Drive locator 搜尋並沒有確認一個同名專用 repo 作為 Dynamic World Simulator mainline。

因此必須凍結：

\[
\boxed{
Söldnerschild
\neq
VerifiedCurrentWorldRuntimeRepository
}
\]

它可以是：

- benchmark；
- game reconstruction target；
- future dynamic-world application；

但不能因為它適合測世界模擬，就把它和 `compilableworld-runtime-mvp` 混成同一專案。

---

# 28. `thisoneisneok`

**Verified GitHub anchor**

```text
kakon77777-commits/thisoneisneok
```

它是一個大型網站 repository。

MSSP_Board README 明確將 MSSP 網站條目視為更完整的 field-lab reference。

因此它應被定位為：

\[
\boxed{
PublicResearch/DocumentationSurface
}
\]

而不是：

\[
WorldRuntime
\]

---

# 29. `mssp-tdd-apr`

**Verified GitHub anchor**

```text
kakon77777-commits/mssp-tdd-apr
```

這是工程／驗證 workflow 相關 repo。

它不能與：

\[
MSSPArchitecture
\]

本身混淆。

所以：

\[
\boxed{
mssp\text{-}tdd\text{-}apr
=
EngineeringMethodology
}
\]

不是 World Runtime，也不是 Domain system。

---

# 30. 搜尋時的三層 Locator Strategy

未來找任何概念，不要只打一個名稱。

採：

\[
\boxed{
Name
+
Role
+
Era
}
\]

三層查找。

例如找 MSSP：

```text
MSSP
MSSP RDR
Dynamic MSSP
MSSP runtime
MSSP TMS
```

找世界 Runtime：

```text
project-mssp-world-runtime
compilableworld-runtime-mvp
MSSP modular world runtime
world state machine
```

找 FDCS：

```text
FDCS
FDCS 2.0
分形動態因果系統
平行剪枝
混合本體論
```

找 UNPNP2：

```text
UNPNP-II
UNPNP2
observer scale
chart-relative
dynamic unitization
One-All
```

找 RDSS：

```text
RDSS
ON_RDSS
Operator_Native_RDSS
type effect
branch quotient
```

---

# 31. Era Tagging

搜尋結果必須標記大致 era。

例如：

```text
Historical MSSP
Dynamic MSSP
MSSP×RDR
MSSPXRDRXUNP
CRDWS Canonical v1
```

不能把 2025 的 MSSP 文件與 2026-09 的新 CRDWS 角色定義無差別混合。

---

# 32. Canonical vs Historical

建議每份被抽取的資料先分類：

```text
canonical-current
current-engineering
historical-active
superseded-reference
adjacent-research
unknown
```

若不確定：

\[
\boxed{
Unknown
>
FalseCanonicalization
}
\]

---

# 33. Project Locator Table

| 名稱 | Verified Locator | 現階段角色 | 不可混淆 |
|---|---|---|---|
| CRDWS / Dynamic World Simulator Canonical v1 | Paper 01–08 | 新最高層 world simulator architecture | 不等於現有單一 repo |
| compilableworld-runtime-mvp | GitHub repo + `project-mssp-world-runtime.md` | Current executable world Runtime anchor | 不等於完整 CRDWS |
| CompilableWorld-Evennia-Prototype | GitHub repo + `project-mud-world-engineering.md` | Superseded predecessor/reference | 不再是 mainline |
| mssp-game-computer-runtime-mvp | GitHub repo | Windows game Computer Use MCP | **不是 world simulator Runtime** |
| mssp-core | GitHub repo | MSSP core anchor/bootstrap | 不代表所有 MSSP 歷史/最新理論 |
| MSSP_Board | GitHub repo | AI field lab / probes / attacks | 不是 canonical Runtime |
| thisoneisneok | GitHub/site | public research/documentation surface | 不是 Runtime |
| SEDB | GitHub repo | semantic/schema evolution infrastructure | 不是 transient World StateStore |
| ai-world-assembly | GitHub repo | integration / generation / validation / repair / orchestration | 不是 World Runtime |
| RDSS | Drive research corpus | adjacent/higher-level formal research line | 不等於 MSSPXRDRXUNP |
| FDCS | Drive research corpus | dynamic causal / pruning / current resolution role | 不等於 UNPNP2，也不是普通 graphics LOD |
| UNPNP-II / UNPNP2 | Drive crystals/open loops + current canonical series | open unitization/classification/path-space research | 不等於 Runtime |
| mssp-tdd-apr | GitHub repo | engineering methodology | 不等於 MSSP core |

---

# 34. Non-Confusion Matrix

## 34.1 CRDWS vs CompilableWorld

\[
CRDWS
=
TargetArchitecture
\]

\[
CompilableWorld
=
CurrentExecutableRuntimeFoundation
\]

所以：

\[
\boxed{
CRDWS
\neq
CompilableWorld
}
\]

---

## 34.2 CompilableWorld vs AWA

\[
CompilableWorld
=
Execute/Commit
\]

\[
AWA
=
Assemble/Generate/Validate/Repair
\]

所以：

\[
\boxed{
Executor
\neq
Assembler
}
\]

---

## 34.3 SEDB vs CompilableWorld

\[
SEDB
=
Semantic/SchemaEvolution
\]

\[
CompilableWorld
=
RuntimeState/Action/Event
\]

所以：

\[
\boxed{
SemanticTruth
\neq
RuntimeTransitionState
}
\]

---

## 34.4 MSSP vs TMS

\[
MSSP
=
CapabilityCompositionArchitecture
\]

\[
TMS
=
ExecutableCapabilityModule
\]

所以：

\[
\boxed{
CompositionSystem
\neq
CapabilityInstance
}
\]

---

## 34.5 UNPNP2 vs FDCS

\[
UNPNP2
=
PotentialStructure/UnitizationSpace
\]

\[
FDCS
=
ActiveResolutionGovernance
\]

所以：

\[
\boxed{
PossibleDepth
\neq
CurrentlyComputedDepth
}
\]

---

## 34.6 RDSS vs CRDWS

\[
RDSS
=
AdjacentFormalResearch
\]

\[
CRDWS
=
WorldSimulatorArchitecture
\]

可以互相輸入，

但：

\[
\boxed{
RDSS
\neq
CRDWS
}
\]

---

## 34.7 mssp-game-computer-runtime vs compilableworld-runtime

前者：

\[
ComputerUseForGames
\]

後者：

\[
ExecutableWorldRuntime
\]

所以：

\[
\boxed{
GameControl
\neq
GameWorldSimulation
}
\]

---

# 35. 找不到 Repo 時的規則

若搜尋：

```text
RDSS
UNPNP2
FDCS
MSSPXRDRXUNP
```

沒有同名 GitHub repo，

禁止：

- 猜 repo 名；
- 把最相近 repo 當成它；
- 創造不存在的 GitHub URL；
- 把 Drive document line 說成 codebase。

應回答：

```text
No verified same-name repository found.
Search Drive/document corpus with these keywords instead.
```

因此：

\[
\boxed{
NoRepoFound
\neq
ProjectDoesNotExist
}
\]

也：

\[
\boxed{
NoRepoFound
\neq
PermissionToInventRepo
}
\]

---

# 36. 搜尋 duplicate files 的規則

Drive 已出現多份同名或近同名 MSSP / RDSS / FDCS 文件。

例如：

```text
11_從靜態MSSP到動態MSSP...
02_MSSP_RDR_RUNTIME_ARCHITECTURE.md
```

存在多個副本。

因此搜尋命中多份時：

1. 比較 `updated_at`；
2. 比較 file size；
3. 找 project locator / canonical handoff；
4. 不因建立時間較晚就自動說是新版；
5. 如內容相同，標記 duplicate/mirror；
6. 若內容衝突，保留兩者並做 provenance comparison。

---

# 37. Project Memory / Locator Files 的角色

Drive 中：

```text
project-mssp-world-runtime.md
project-mud-world-engineering.md
```

這種文件不是理論論文本身。

它們是：

\[
\boxed{
NavigationMetadata
}
\]

其價值是：

- 指向 mainline；
- 指向 predecessor；
- 指向 local folder；
- 指向 GitHub；
- 記錄 superseded 狀態。

未來應優先拿這類 locator 解決「到底是哪個 repo」問題。

---

# 38. 研究文件 vs 工程證據

研究文件可以說：

> 應該這樣設計。

Engineering repo 要回答：

> 目前真的做到哪裡？

因此：

\[
\boxed{
TheoryClaim
\neq
ImplementedCapability
}
\]

例如：

Paper 04 定義 FDCS resolution vector，

不代表目前 `compilableworld-runtime-mvp` 已實作全部 resolution vector。

Paper 05 定義 TMS capability contract，

也不代表舊 TMS loader 已符合所有欄位。

這正是 Paper 07 要 audit 的原因。

---

# 39. Current Canonical Migration Direction

目前推薦的 lineage：

```text
Historical MSSP
      ↓
Dynamic MSSP
      ↓
MSSP + RDR
      ↓
MSSP Modular World Runtime
      ↓
compilableworld-runtime-mvp
      ↓
[Paper 07 Migration Audit]
      ↓
MSSPXRDRXUNP / UNPNP2 / FDCS / TMS Integration
      ↓
CRDWS Implementation
```

同時旁路：

```text
SEDB ----------------------→ Semantic Authority
AWA -----------------------→ Assembly / Generation / Repair
RDSS ----------------------→ Formal / Operator Research
FDCS corpus ---------------→ Resolution / Dynamic Causal Methods
UNPNP-II corpus -----------→ Dynamic Unitization / Open Structure
Presentation targets ------→ Experience / Projection
```

它們不是被「吃掉」，

而是按 responsibility 接入。

---

# 40. Current Implementation Anchor vs Future Target

目前最重要 distinction：

\[
\boxed{
CurrentAnchor
=
compilableworld\text{-}runtime\text{-}mvp
}
\]

而：

\[
\boxed{
FutureTarget
=
CRDWS
}
\]

Paper 07 要回答：

\[
CurrentAnchor
\rightarrow
FutureTarget
\]

到底：

- 哪些保留；
- 哪些擴充；
- 哪些 deprecated；
- 哪些需要新 layer；
- 哪些不應放進 Runtime core。

---

# 41. Recommended Search Queries

## MSSP core/history

```text
MSSP
MSSP Core
MSSP 0.1 1.0
Dynamic MSSP
靜態MSSP 動態MSSP
Mother-Set Subset Paradigm
```

## RDR / XRDR

```text
MSSP RDR
MSSP_RDR_RUNTIME_ARCHITECTURE
RDR dispatch
權威結構 執行派發
XRDR
```

## World Runtime

```text
project-mssp-world-runtime
compilableworld-runtime-mvp
MSSP Modular World Runtime
可編譯世界
world state machine
世界狀態機
```

## World State Theory

```text
從狀態機到世界狀態機
母AI世界狀態機
遞歸動態狀態
狀態 容器 存在
計算機宇宙 世界狀態
```

## FDCS

```text
FDCS
FDCS 2.0
分形動態因果系統
平行剪枝
混合本體論
MWT Ledger
CausalOps
```

## UNPNP2

```text
UNPNP-II
UNPNP2
observer scale
chart-relative
dynamic unitization
One-All
True ETN
```

## RDSS

```text
RDSS
ON_RDSS
Operator_Native_RDSS
RDSS Operatorization
Type Effect
Branch Quotient
```

## TMS

```text
TMS
MSSP TMS
mechanism module
capability module
world module
```

## SEDB

```text
SEDB
Semantic Evolution Database
Unbounded Dynamic Field
field lifecycle
schema evolution
```

## AI World Assembly

```text
ai-world-assembly
AI World Assembler
Dynamic Asset Graph
CSC-OCM
multi-world orchestration
```

---

# 42. AI Retrieval Procedure

未來 AI 被要求：

> 「找回那個世界模擬專案。」

應按：

```text
Step 1
先判定使用者說的是：
- world runtime?
- computer-use runtime?
- assembler?
- semantic database?
- research theory?

Step 2
查 Project Locator / Canonical Series。

Step 3
查 GitHub exact repo。

Step 4
查 Drive exact title / keywords。

Step 5
標記 source era。

Step 6
列出候選，不自行合併。

Step 7
只有 evidence 足夠時才宣告：
"This is the project."
```

---

# 43. 「名字相近」不是證據

例如：

```text
mssp-game-computer-runtime-mvp
```

和：

```text
mssp-world-runtime
```

名字都包含 MSSP / runtime，

但 role 完全不同。

因此：

\[
\boxed{
StringSimilarity
\neq
ProjectIdentity
}
\]

---

# 44. 「概念相近」也不是同一專案

例如：

RDSS 與 Dynamic World State 都談 dynamic state。

但：

\[
ConceptualOverlap
\neq
ProjectIdentity
\]

同樣：

SEDB 也談 dynamic fields / evolution，

不代表它就是 FDCS 或 World Runtime。

---

# 45. 「被某專案使用」不等於「是那個專案」

例如：

CRDWS 未來可以使用：

- SEDB；
- CompilableWorld；
- AWA；
- RDSS operator；
- FDCS；
- UNPNP2。

但：

\[
Uses(X)
\neq
Is(X)
\]

---

# 46. Canonical Project Roles

目前建議凍結：

\[
\boxed{
CRDWS
=
WorldSimulationArchitecture
}
\]

\[
\boxed{
CompilableWorld
=
ExecutableWorldRuntimeFoundation
}
\]

\[
\boxed{
SEDB
=
SemanticEvolutionInfrastructure
}
\]

\[
\boxed{
AWA
=
AssemblyGenerationValidationRepair
}
\]

\[
\boxed{
MSSP
=
CapabilityCompositionArchitecture
}
\]

\[
\boxed{
TMS
=
ExecutableCapabilityModule
}
\]

\[
\boxed{
XRDR
=
RecursiveResolutionDispatchRecomposition
}
\]

\[
\boxed{
FDCS
=
DynamicResolutionGovernance
}
\]

\[
\boxed{
UNPNP2
=
OpenDynamicUnitizationClassificationSpace
}
\]

\[
\boxed{
RDSS
=
AdjacentFormalRecursiveDynamicStateResearch
}
\]

\[
\boxed{
mssp\text{-}game\text{-}computer\text{-}runtime
=
GameComputerUseRuntime
}
\]

---

# 47. Canonical Non-Confusion Invariants

## P1 — Related Does Not Mean Identical

\[
\boxed{
Related
\neq
Identical
}
\]

---

## P2 — Successor Does Not Erase Predecessor

\[
\boxed{
Successor
\neq
HistoricalRewrite
}
\]

---

## P3 — Repository Name Does Not Define Architecture Role

\[
\boxed{
RepoName
\neq
RoleEvidence
}
\]

---

## P4 — No Verified Repo Means No Invented Repo

\[
\boxed{
NoVerifiedRepo
\Rightarrow
DoNotInvent
}
\]

---

## P5 — Current Canonical Architecture Has Priority for New Implementation

\[
\boxed{
Paper01\text{-}08
>
HistoricalArchitecture
}
\]

for new CRDWS implementation decisions.

---

## P6 — Historical Sources Remain Provenance

\[
\boxed{
Superseded
\neq
Delete
}
\]

---

## P7 — Theory Is Not Implementation

\[
\boxed{
Theory
\neq
ImplementedCapability
}
\]

---

## P8 — Integration Is Not Identity Collapse

\[
\boxed{
Integrate(A,B)
\neq
A=B
}
\]

---

## P9 — World Runtime Is Not Computer Use Runtime

\[
\boxed{
WorldSimulation
\neq
GUIControl
}
\]

---

## P10 — Assembly Is Not Runtime

\[
\boxed{
Assembler
\neq
Executor
}
\]

---

## P11 — Semantic Truth Is Not Transient Runtime State

\[
\boxed{
SemanticAuthority
\neq
RuntimeStateAuthority
}
\]

---

## P12 — Current Role Must Be Tagged With Era

\[
\boxed{
Meaning
=
Term
+
Context
+
Era
}
\]

---

# 48. Paper 06 canonical navigation map

```text
                         ┌─────────────────────┐
                         │ CRDWS Paper 01–08   │
                         │ Current Canonical   │
                         └──────────┬──────────┘
                                    │
                 ┌──────────────────┼──────────────────┐
                 │                  │                  │
                 ▼                  ▼                  ▼
        MSSP/RDR lineage       World Runtime       Resolution/Formal
                 │                  │                  │
        MSSP whitepapers        project-mssp-       FDCS corpus
        Dynamic MSSP            world-runtime       UNPNP-II
        MSSP_RDR docs               │                RDSS corpus
                 │                  ▼
                 │        compilableworld-runtime-mvp
                 │                  │
                 └──────────┬───────┘
                            │
                            ▼
                    Future CRDWS Runtime
                            │
          ┌─────────────────┼──────────────────┐
          ▼                 ▼                  ▼
        SEDB               AWA             Presentation
    Semantic Truth     Assembly/Repair      Experience
```

旁支：

```text
CompilableWorld-Evennia-Prototype
    = predecessor/reference

mssp-game-computer-runtime-mvp
    = game Computer Use
    ≠ world simulation runtime

MSSP_Board
    = field lab
    ≠ runtime mainline
```

---

# 49. 與 Paper 07 的接口

Paper 06 已解決：

> 到底該找哪個專案？

下一篇才真正做：

> 找到之後，哪些東西要留下？

因此 Paper 07 將以：

```text
compilableworld-runtime-mvp
```

以及相關 MSSP / RDR / world-state historical docs 作主要 audit base，

對照 Paper 01–05：

\[
Existing
\rightarrow
Keep
\]

\[
Existing
\rightarrow
Adapt
\]

\[
Existing
\rightarrow
Replace
\]

\[
Missing
\rightarrow
Add
\]

特別要檢查：

- 現有 TMS loader；
- State Machine；
- Module Contract；
- ActionIR；
- StateDelta；
- EventIR；
- Entity transaction；
- Runtime scheduler；
- world structure representation；
- domain representation；
- resolution representation；
- cross-domain causality；
- projection boundary。

---

# 50. Source Verification Notes — 2026-09-10

本文件撰寫前已透過 connected GitHub / Google Drive 實際確認以下 locator。

## GitHub confirmed

```text
kakon77777-commits/mssp-core
kakon77777-commits/MSSP_Board
kakon77777-commits/mssp-game-computer-runtime-mvp
kakon77777-commits/compilableworld-runtime-mvp
kakon77777-commits/CompilableWorld-Evennia-Prototype
kakon77777-commits/SEDB
kakon77777-commits/ai-world-assembly
kakon77777-commits/mssp-tdd-apr
kakon77777-commits/thisoneisneok
```

## Drive confirmed

```text
project-mssp-world-runtime.md
project-mud-world-engineering.md
MSSP-0.1-to-1.0-Technical-Whitepaper.zh-TW.md
11_從靜態MSSP到動態MSSP_讓架構角色成為可觀察狀態.md
02_MSSP_RDR_RUNTIME_ARCHITECTURE.md
05_權威結構與執行派發_格子語言CAIR_MSSP與RDR的接合_v0.1.md

FDCS_2.0_MWT_Ledger_Native_Revision_Baseline_v0.1_ZH.md
FDCS（分形動態因果系統）化學版.docx
FDCS 2.0終極版：平行剪枝與混合本體論計算(舊).docx

ON_RDSS_Research_Handoff_v1.0.md
RDSS_Operatorization_Translation_Matrix_v0.1.md
Operator_Native_RDSS_Primitive_Algebra_v0.1.md

04_從狀態機到世界狀態機_AI為何不應每輪重新理解世界.md
02_母AI世界狀態機與子智能網路.md
狀態、容器與存在：遞歸動態狀態系統的總命題.md

01_Aletheia_Conversation_Crystals
02_Aletheia_Async_Open_Loops
    → contain UNPNP-II related current research references
```

---

# 結論

這個研究線真正的風險之一，不是「資料找不到」。

而是：

\[
\boxed{
資料太多，而且名字彼此太接近
}
\]

MSSP、Dynamic MSSP、MSSP×RDR、XRDR、TMS、FDCS、UNPNP2、RDSS、SEDB、CompilableWorld、AI World Assembly、Game Computer Runtime 都彼此有關。

但「有關」不能被 AI 簡化成「都是同一個」。

因此本文件最重要的永久規則是：

\[
\boxed{
Related
\neq
Identical
}
\]

在目前已確認的工程世界中：

\[
\boxed{
compilableworld\text{-}runtime\text{-}mvp
=
CurrentExecutableWorldRuntimeAnchor
}
\]

而新的：

\[
\boxed{
CRDWS
=
FutureCanonicalWorldSimulationTarget
}
\]

兩者之間需要 Paper 07 的 migration audit，

而不是直接 rename。

同時：

\[
\boxed{
mssp\text{-}game\text{-}computer\text{-}runtime
\neq
WorldRuntime
}
\]

是這次最重要的防混淆結論之一。

SEDB、AWA、RDSS、FDCS、UNPNP2 也都保留自己的 identity 與 authority。

最終正確的研究方法不是：

> 「找一個最像的名稱，然後全部塞進去。」

而是：

\[
\boxed{
Locate
\rightarrow
Classify
\rightarrow
PreserveLineage
\rightarrow
CompareRoles
\rightarrow
IntegrateWithoutIdentityCollapse
}
\]

---

**End of Paper 06**
