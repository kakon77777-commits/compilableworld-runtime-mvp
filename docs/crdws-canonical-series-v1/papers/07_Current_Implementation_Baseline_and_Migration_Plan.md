# Paper 07 — Current Implementation Baseline and Migration Plan

**系列：Dynamic World Simulator Canonical Series v1**  
**文件定位：Current Runtime Audit / CRDWS Migration Baseline**  
**狀態：Canonical Migration Baseline**  
**版本：v1.0**  
**日期：2026-09-10**

---

## 摘要

Paper 01–05 已經建立新版 Dynamic World Simulator 的核心目標：

\[
\boxed{
Composable\ Recursive\ Dynamic\ World\ Simulator
}
\]

並逐步凍結：

\[
World
=
RecursiveCompositionOfDynamicDomains
\]

\[
WorldEvolution
=
StateEvolution
+
StructureEvolution
\]

\[
Domain
\neq
TMS
\]

\[
FullExistence
\neq
FullResolution
\]

\[
TMS
=
ExecutableWorldCapabilityModule
\]

Paper 06 則重新確認專案血統，並指出目前真正應作為 world-engine 工程主線檢查的 repository 是：

```text
kakon77777-commits/compilableworld-runtime-mvp
```

而不是名稱相近但用途不同的：

```text
kakon77777-commits/mssp-game-computer-runtime-mvp
```

本文件因此正式回答：

> **現有 CompilableWorld / MSSP Modular World Runtime 已經做到什麼？哪些必須保留？哪些只需擴充？哪些概念不能硬塞進舊模型？若要遷移到 MSSPXRDRXUNP / UNPNP2 / FDCS / TMS 的新版 CRDWS，正確施工順序是什麼？**

本次 audit 的最重要結論是：

\[
\boxed{
DoNotRewriteTheValidatedRuntimeKernel
}
\]

現有 Runtime 已經具備大量新版仍然需要的核心性質：

- Authoring / Compiled Package / Runtime State 分離；
- versioned schema；
- Compiler；
- Entity Registry；
- StateStore；
- ActionIR；
- StateDelta；
- EventIR；
- ModuleContract；
- atomic commit；
- EventBus；
- EventLog；
- Snapshot / Replay；
- Scheduler；
- FunctionIR；
- ScenarioIR；
- Scoped StateIR；
- bounded Action behavior graph；
- read-only projection；
- entity transaction extension。

真正需要新增的是：

\[
\boxed{
WorldCompositionPlane
+
DynamicResolutionPlane
+
ResolutionAwareCapabilityPlane
}
\]

因此 migration 應採：

\[
\boxed{
KeepKernel
\rightarrow
AddContracts
\rightarrow
AddAdapters
\rightarrow
ProveOneDomain
\rightarrow
ProveCrossDomain
\rightarrow
AddDynamicResolution
\rightarrow
AddStructureEvolution
}
\]

而不是：

\[
OldRuntime
\rightarrow
Delete
\rightarrow
RewriteEverything
\]

---

# 1. Audit Source Baseline

本文件使用的主要 executable baseline：

```text
repository:
kakon77777-commits/compilableworld-runtime-mvp

default branch:
master

audited exact commit:
cf37f539e0807499e8b337f80a5f152324c087f2

commit:
Phase 10: transaction-safe runtime entity creation

date:
2026-09-09
```

這是本文件建立時 repository 的最新確認 commit。

該 commit 新增：

```text
entity_transaction/v0.1
EntityDelta(create)
EntityTransactionRuntime
```

使：

\[
StateDelta
+
EntityDelta
+
EventIR
\]

第一次能位於同一 rollback boundary。

---

# 2. Historical Project Locator

Drive 的：

```text
project-mssp-world-runtime.md
```

明確將：

```text
compilableworld-runtime-mvp
```

定位為：

```text
CompilableWorld-Evennia-Prototype
```

的 successor，

並記錄它是 Neo.K 的 MUD / world-engine development mainline。

這一點對 migration 很重要。

因為新版 CRDWS 不應回頭從 Evennia prototype 重新出發。

正確 lineage 是：

```text
CompilableWorld-Evennia-Prototype
        ↓ superseded
MSSP Modular World Runtime
        ↓
compilableworld-runtime-mvp
        ↓
CRDWS migration
```

---

# 3. Migration Classification

本文件使用六種判定：

## KEEP

現有設計與新版 CRDWS 高度相容。

應保留，不重寫。

## ADAPT

核心方向正確，

但 contract 或 responsibility 需要升版。

## ADD

現有 Runtime 尚無此能力，

應以 additive layer 新增。

## REPLACE

現有表示會阻礙新版架構，

需要逐步淘汰。

本次 audit 的結論是：

> REPLACE 項目非常少。

## DO NOT MERGE

兩個概念相鄰，

但不能因 migration 而揉成一個 authority。

## DEFER

新版長期需要，

但現在沒有足夠 concrete gap 支持立刻實作。

---

# 4. Executive Migration Verdict

整體 verdict：

| Existing Area | Verdict |
|---|---|
| Authoring / Compiled / Runtime separation | KEEP |
| JSON/CSV/Manifest Compiler | KEEP + ADAPT |
| Versioned Schema Registry | KEEP |
| Entity Registry | KEEP |
| StateStore | KEEP + ADAPT |
| ActionIR | KEEP |
| StateDelta | KEEP |
| EventIR / EventBus / EventLog | KEEP |
| ModuleContract | KEEP + ADAPT toward TMS contract |
| Atomic commit / optimistic concurrency | KEEP |
| EntityTransactionRuntime | KEEP + EXTEND LATER |
| Snapshot / Replay | KEEP + ADAPT |
| Scheduler | KEEP + ADAPT toward Multi-Rate |
| FunctionIR | KEEP |
| ScenarioIR | KEEP + EXTEND |
| Quest / Scoped StateIR | KEEP as bounded FSM capability |
| Action Behavior v0.7 | KEEP as bounded Action capability |
| UI / Web / MCP projection separation | KEEP |
| Agent Memory Kernel | DO NOT MERGE into World Truth |
| MCP distributed service work | DO NOT MERGE with CRDWS core |
| Fixed current mechanic modules | KEEP as current TMS ancestors |
| Open World Domain Graph | ADD |
| UNPNP2 classification binding | ADD |
| FDCS resolution state/governance | ADD |
| Resolution-aware TMS families | ADD |
| Aggregate ↔ Microstate transition | ADD |
| Multi-rate domain execution | ADD |
| Cross-domain causal contracts | ADD |
| Domain structure mutation | ADD LATER |
| Dynamic arbitrary recursive Action Graph | DEFER |
| Distributed consensus for world truth | DEFER |
| Canonical AI auto-promotion | DO NOT ADD |

---

# 5. What Must Be Preserved First

現有 `AGENTS.md` 已經包含大量與新版高度一致的不變量。

其中最重要的是：

```text
Authoring Layer
≠
Compiled Package
≠
Runtime State
```

這一條完全保留。

因此：

\[
\boxed{
SourceTruth
\neq
CompiledTruth
\neq
RuntimeTruth
}
\]

新版 Domain Graph、FDCS policy、TMS contract 也都必須遵守同一原則。

---

# 6. KEEP — Authoring → Compile → Runtime Boundary

現有流程：

```text
JSON / CSV / Manifest
        ↓
Compiler
        ↓
Runtime Package
        ↓
World Runtime
```

這其實正是 CRDWS 很需要的「世界規則不能在 Runtime 中偷偷出現」的基礎。

所以：

\[
\boxed{
ContractsBeforeExecution
}
\]

不只不能移除，

反而要擴大。

未來新增：

```text
domains.json
domain-relations.json
tms-bindings.json
resolution-policies.json
causal-contracts.json
```

時，

也應先進：

\[
AuthoringSchema
\]

再進：

\[
Compiler
\]

最後才進 Runtime Package。

---

# 7. KEEP — Versioned External Schemas

現有 repo 已經有：

```text
schemas/
```

包含：

- runtime-package；
- functions；
- scenarios；
- state-machines；
- action-behaviors；
- entities；
- rooms；
- exits；
- items；
- studio contracts；
- MCP contracts。

這個 pattern 完全應保留。

未來新增：

```text
world-domain-graph/v0.1
tms-capability/v0.1
resolution-policy/v0.1
resolution-state/v0.1
causal-link/v0.1
```

都應延續：

\[
\boxed{
VersionedFailClosedContract
}
\]

---

# 8. KEEP — ActionIR

目前：

\[
ActionIR
\]

是玩家／AI／UI 進入 Runtime 的正式 intent boundary。

Paper 01–05 沒有提出任何需要取代它的理由。

因此：

\[
\boxed{
ActionIR
=
Keep
}
\]

未來可擴充：

- Domain-aware metadata；
- world time context；
- resolution context；
- TMS routing metadata；

但不應讓 UI / AI 改回：

```text
直接呼叫 Python function
```

或：

```text
直接改 StateStore
```

---

# 9. KEEP — StateDelta

現有 Module 的核心模式：

\[
module.evaluate(ActionIR)
\rightarrow
StateDelta
\]

再由 Kernel：

\[
StateStore.commit()
\]

這與 Paper 05 的 TMS contract 幾乎完全一致。

因此：

\[
\boxed{
TMS
\rightarrow
Delta
\rightarrow
RuntimeCommit
}
\]

應成為新版延續線。

---

# 10. KEEP — EventIR

現有 Runtime 已將跨模組合作建立為：

\[
Module_A
\rightarrow
EventIR
\rightarrow
Module_B
\]

而不是：

\[
Module_A
\rightarrow
Module_B.internalMethod()
\]

這是 CRDWS cross-domain causality 的正確祖先。

Paper 03 已凍結：

\[
CrossDomainInfluence
\neq
ArbitraryForeignWrite
\]

現有 EventIR 架構正好可以成為新版：

\[
CrossDomainCausalSignal
\]

的第一層 transport。

所以：

\[
\boxed{
EventIR
=
KeepAndGeneralize
}
\]

---

# 11. KEEP — commit_reaction()

現有 Runtime 已允許 Event subscriber：

\[
Event
\rightarrow
Reaction
\rightarrow
StateDelta
\]

仍然走 Runtime commit boundary。

這一點非常適合：

```text
Military.mobilization
    ↓ EventIR
Economy.labor
    ↓ own transition
workforce changes
```

而不是 Military 直接寫 Economy state。

因此：

\[
\boxed{
commit\_reaction
}
\]

是未來 cross-domain causality 可重用的重要 primitive。

---

# 12. KEEP — State Ownership and Permission Checks

現有 Runtime 已要求 ModuleContract write scope。

這和 Paper 03：

\[
OneCanonicalOwnerPerStateDimension
\]

可以直接接。

未來應把：

```text
namespace write scope
```

進一步 formalize 成：

```text
domain-owned state dimension
```

但不應移除現有 allowlist。

---

# 13. KEEP — Atomic Commit

現有 Runtime 的核心保證：

\[
StateDelta
\rightarrow
AtomicCommit
\]

EventLog append failure 時可 rollback。

這是新版所有高階 transaction 的必要底座。

因此：

\[
\boxed{
Atomicity
=
Foundation
}
\]

---

# 14. KEEP — EntityTransactionRuntime

2026-09-09 新增：

\[
EntityDelta(create)
\]

以及：

\[
entity\_transaction/v0.1
\]

目前 transaction：

```text
module.evaluate(ActionIR)
→ validate StateDelta + EntityDelta
→ commit StateDelta
→ create Entity
→ append state/entity/module events
→ publish
```

任何失敗：

```text
StateStore
EntityRegistry
dynamic_entities
EventLog
```

回到 pre-action state。

這正是 Paper 03：

\[
StructureMutationMustBeFirstClassAndTransactional
\]

的第一個 concrete proof。

所以：

\[
\boxed{
EntityTransactionRuntime
=
Keep
}
\]

---

# 15. ADAPT LATER — EntityDelta Beyond Create

目前 v0.1 明確只有：

```text
create
```

不包含：

- remove；
- despawn；
- replace。

這是正確的 bounded contract。

新版 CRDWS 不應因為 Structure Evolution 概念變大，就一次擴成：

```text
create/delete/move/retype/merge/split/everything
```

應維持：

\[
\boxed{
GapDrivenExtension
}
\]

等真正 world-domain use case 證明需要 remove/despawn 時再升版。

---

# 16. KEEP — EventLog / Snapshot / Replay

大型動態世界一定需要：

\[
History
\]

而不是只保留 current state。

現有：

- EventLog；
- Snapshot；
- Replay；

都應保留。

Paper 04 未來新增 resolution transition 後，

需要把：

```text
resolution decisions
summary checkpoints
refinement provenance
```

也納入 replay evidence。

所以 verdict：

\[
\boxed{
KeepCore
+
AdaptMetadata
}
\]

---

# 17. KEEP — FunctionIR

現有 FunctionIR 是 restricted pure numeric expression tree。

這個方向和 TMS philosophy 一致：

\[
PureComputation
\neq
WorldSideEffect
\]

未來：

- economy formula；
- population model；
- combat；
- production；
- tax；
- aggregate conversion；

都可以繼續使用 pure FunctionIR 或其升版。

不要因為 AI 變強就直接：

```text
eval(arbitrary_python)
```

---

# 18. KEEP — ScenarioIR

現有 ScenarioIR 走：

\[
Given
\rightarrow
When(ActionIR)
\rightarrow
Then(State/Event)
\]

而且不另開第二條世界規則。

這對 CRDWS 非常重要。

未來每一個新增：

- Domain；
- TMS；
- FDCS transition；
- cross-domain causal link；

都應有 scenario witness。

因此：

\[
\boxed{
ScenarioIR
=
PrimaryMigrationEvidenceMechanism
}
\]

---

# 19. KEEP — Scoped StateIR

目前已支援：

```text
World
Region
Scene
Entity
System
```

五種 owner scope。

每台 machine：

- versioned；
- bounded；
- compiler validated；
- snapshot/replay；
- EventIR driven；
- explicit authority。

這是非常好的既有資產。

---

# 20. Important Boundary — Scoped StateIR Is Not Domain Graph

這也是 migration 中必須避免的第一個錯誤。

目前：

```text
owner_scope = world / region / scene / entity / system
```

描述的是：

\[
StateOwnershipScope
\]

不是：

\[
WorldDomainOntology
\]

例如：

```text
owner_scope=system
owner_id=system.economy
```

即使可以暫時表示某一 system state，

也不等於 Paper 03 的：

\[
DomainGraph
\]

因為 Domain Graph 還需要：

- hierarchy；
- cross-domain relation；
- capability binding；
- causal edge；
- activation；
- split/merge；
- resolution policy；
- provenance。

所以：

\[
\boxed{
ScopedStateIR
\neq
DomainGraph
}
\]

---

# 21. KEEP — Action Behavior v0.7

現有 Action behavior 已有：

- static phase DAG；
- bounded branch；
- priority；
- child primitive action；
- retry；
- timeout；
- cancel；
- interrupt；
- snapshot；
- replay。

這是一個很強的「長時間 Action」能力。

應保留。

---

# 22. Do Not Overgeneralize Action DAG

Action behavior 文件自己已明確標示目前不是：

- dynamic Action Graph；
- recursive Action Graph；
- nested graph；
- parallel/synchronizing join；
- arbitrary guard/effect script。

這很好。

CRDWS 的 recursive world composition 不代表：

> Action Graph 也必須立刻變成無限遞歸。

兩者是不同問題。

所以：

\[
\boxed{
RecursiveWorldStructure
\not\Rightarrow
ImmediateRecursiveActionGraph
}
\]

此項維持：

\[
DEFER
\]

直到真實 use case 證明必要。

---

# 23. KEEP — Existing Mechanism Modules

目前已存在：

- room；
- movement；
- door；
- inventory；
- health；
- combat；
- dialogue；
- quest；
- magic / status 等後續能力。

這些不應因新版 TMS 規格而全部重寫。

更合理：

\[
ExistingModule
\rightarrow
TMSContractAdapter
\]

先證明：

- identity；
- reads；
- writes；
- events；
- dependencies；
- timescale；
- resolution support；

再決定是否需要 refactor。

---

# 24. ADAPT — ModuleContract → TMS Contract

這是第一個主要 migration work。

現有 ModuleContract 已經有重要基礎：

- module identity；
- actions；
- reads；
- writes；
- kernel requirements。

Paper 05 的 TMS contract 更完整：

\[
TMS=
(
Identity,
Version,
Capability,
DomainBindings,
Inputs,
Reads,
Writes,
Events,
Operators,
Constraints,
Timescale,
Dependencies,
ResolutionSupport,
Approximation,
Authority,
Determinism,
Provenance
)
\]

因此：

\[
\boxed{
ModuleContract
\rightarrow
TMSContractVNext
}
\]

是 ADAPT，

不是 REPLACE。

---

# 25. TMS Compatibility Adapter First

不要立刻改所有 module source。

先建立：

```text
Existing ModuleContract
        ↓
TMS Compatibility Adapter
        ↓
TMS Contract Projection
```

這樣可以檢查：

- 哪些欄位已有；
- 哪些可以 deterministic derive；
- 哪些 truly missing。

只有真正缺的才加入 core contract。

---

# 26. ADD — Domain Graph

這是 Paper 03 與現有 Runtime 最大的結構缺口。

目前世界有：

- rooms；
- entities；
- state machines；
- mechanism modules；

但沒有一個正式：

\[
WorldDomainGraph
\]

描述：

```text
economy
military
politics
science
culture
...
```

之間的：

- hierarchy；
- dependency；
- causal relation；
- capability requirements；
- active/inactive；
- resolution binding。

因此第一個新 major contract 應是：

```text
world-domain-graph/v0.1
```

---

# 27. Domain Graph Must Be Additive

不要把：

```text
rooms.csv
entities.csv
state_machines.json
```

全部改成 Domain Graph。

Domain Graph 是上層 composition structure。

它應引用既有 Authoring facts，

而不是取代所有 existing source.

所以：

\[
\boxed{
DomainGraph
=
NewCompositionLayer
}
\]

不是：

\[
DomainGraph
=
UniversalReplacementFormat
\]

---

# 28. Suggested Domain v0.1 Minimal Scope

第一版只需要：

```text
domain_id
title
status
parent_relations
cross_domain_relations
required_capabilities
state_bindings
resolution_policy_ref
authority
```

不要第一版就做：

- AI autonomous split；
- dynamic ontology mutation；
- distributed domain ownership；
- arbitrary formulas。

---

# 29. ADD — Domain Composition Receipt

Compiler 應產生：

\[
DomainCompositionReceipt
\]

至少包含：

```text
world_id
domain_graph_hash
active_domains
capability_requirements
resolved_tms_bindings
resolution_policy_refs
diagnostics
```

這讓 world composition 可驗證。

---

# 30. ADD — UNPNP2 Classification Binding

UNPNP2 不應直接塞進 Kernel。

Paper 02 已定義：

\[
UNPNP2
=
PotentialClassificationSpace
\]

因此正確第一步是：

```text
UNPNP2 Classification Adapter
```

輸出：

```text
classification path
parent/child candidates
cross-link candidates
unknown markers
provenance
```

再由 Domain Graph 決定：

\[
Active
\]

與否。

---

# 31. Do Not Make UNPNP2 Runtime Authority

UNPNP2 可以回答：

> 這個概念可以放在哪？

不能直接回答：

> 這個 Domain 現在必須啟用。

所以：

\[
\boxed{
ClassificationProposal
\neq
DomainActivationAuthority
}
\]

---

# 32. ADD — FDCS Resolution State

目前 Runtime 有：

- state；
- tick；
- scheduler；

但沒有 Paper 04 定義的：

\[
\mathbf{R}
=
(
r_{class},
r_{state},
r_{time},
r_{agent},
r_{relation},
r_{causal},
r_{history},
r_{uncertainty}
)
\]

因此需要新的：

```text
resolution-state/v0.1
```

但第一版不要一次實作 8 維全功能。

---

# 33. Recommended FDCS MVP

第一個 engineering slice 建議只證明三維：

\[
\boxed{
r_{state},
r_{time},
r_{agent}
}
\]

例如：

```text
city economy
```

可在：

```text
summary
cohort
detailed
```

三種 state representation 間切換。

同時改變：

```text
daily
hourly
event-driven
```

執行頻率。

這比直接做完整八維 resolution 更容易形成真 evidence。

---

# 34. ADD — Resolution Policy Contract

例如：

```yaml
resolution_policy:
  domain: world.economy.city
  modes:
    - summary
    - cohort
    - detailed
  promote_on:
    - observer_relevance
    - prediction_error
    - causal_risk
  demote_on:
    - low_activity
    - low_relevance
  minimum_residency_ticks: ...
```

但：

\[
FDCS
\]

只應產：

\[
ResolutionPlan
\]

而不是直接改 world truth。

---

# 35. ADD — Resolution Transition Receipt

每次：

\[
Low
\rightarrow
High
\]

或：

\[
High
\rightarrow
Low
\]

需要：

```text
before
after
trigger
reason
state migration
validation
budget delta
provenance
```

這應像現有 Runtime receipt / event evidence 一樣可 replay。

---

# 36. ADD — Aggregate ↔ Microstate Migration

這是 Paper 04 的核心工程挑戰。

目前 Runtime 比較偏向：

\[
ConcreteEntityState
\]

但大型世界需要：

\[
AggregateState
\leftrightarrow
MicroState
\]

例如：

```text
population.total = 10000
```

升解析後才 materialize：

```text
cohorts
important individuals
local households
```

---

# 37. Do Not Hallucinate Microstate

Refinement 必須滿足：

\[
Aggregate(Refine(S_L))
\approx
S_L
\]

所以需要：

- deterministic refine；
- constrained stochastic refine；
- candidate AI refine；

但 AI refine 預設只能：

\[
Candidate
\]

---

# 38. ADD — Resolution-aware TMS Family

目前一個 mechanism module 通常就是一個 implementation。

未來需要：

```text
capability.economy.market
├─ summary implementation
├─ cohort implementation
└─ detailed implementation
```

所以：

\[
Capability
\rightarrow
TMSFamily
\]

MSSP/XRDR 依 FDCS context 選 implementation。

---

# 39. ADAPT — Scheduler → Multi-Rate Scheduler

現有 Scheduler 已支援：

- delayed action；
- tick；
- cancellation；
- interruption；
- pending action；
- replay。

這是很好的 foundation。

不應重寫。

應擴成：

\[
\boxed{
MultiRateScheduling
}
\]

支援：

```text
event-driven
fixed interval
scheduled calendar
lazy
deferred
high-frequency
low-frequency
```

---

# 40. Multi-Rate Must Not Mean Many Independent Clocks Without Order

如果：

\[
\tau_A\neq\tau_B
\]

仍需要：

- authoritative world time；
- deterministic ordering；
- causal timestamp；
- replay order。

所以現有 tick / EventLog ordering 應保留作底層排序基準。

---

# 41. ADD — Domain Time Policy

Domain 可以宣告：

```text
economy.market -> hourly/event
culture.norm -> weekly
demography -> monthly
combat -> per-action
```

FDCS 可動態調整，

但 Runtime time semantics 必須一致。

---

# 42. ADD — Cross-Domain Causal Contract

現有 EventIR 足以作 transport，

但缺少：

\[
DomainA
\rightarrow
CausalLink
\rightarrow
DomainB
\]

的高層 declaration。

所以需要：

```text
causal-link/v0.1
```

至少描述：

```text
source_domain
event_type
target_domain
consumed_capability
strength/priority
resolution_requirement
provenance
```

---

# 43. Do Not Put Causal Graph in Dynamic Asset Graph

AI World Assembly 的 Dynamic Asset Graph 是：

\[
AssemblyTopology
\]

不是 Runtime causal graph。

因此：

\[
\boxed{
AssetDependency
\neq
WorldCausality
}
\]

CRDWS causal graph 必須是獨立 runtime/world contract。

---

# 44. ADD — Causal Propagation Budget

大型世界的 EventIR 不能無限 propagation。

未來 FDCS / causal layer 需要：

```text
depth limit
importance decay
resolution threshold
budget
```

否則：

\[
OneEvent
\rightarrow
WholeWorldWakeUp
\]

會造成計算爆炸。

---

# 45. ADAPT — StateStore

StateStore 核心 atomic semantics 應 KEEP。

但需要 ADAPT：

- explicit Domain binding；
- representation mode；
- resolution version；
- aggregate/micro lineage；
- owner identity；
- uncertainty metadata。

不要把所有 metadata 都塞入 cell value 本身。

---

# 46. StateStore Should Not Become SEDB

Paper 06 已凍結：

\[
SEDB
\neq
RuntimeStateStore
\]

所以 migration 不能說：

> SEDB 很適合動態欄位，那就用它直接存所有 Runtime state。

SEDB 可以提供：

- semantic field authority；
- schema evolution；
- provenance；

Runtime state 仍保留：

- transaction；
- tick；
- action causality；
- replay；

自己的 authority。

---

# 47. ADD — State Representation Identity

同一 semantic state：

```text
economy.population
```

可能有：

```text
summary representation
cohort representation
individual representation
```

需要：

\[
RepresentationIdentity
\]

以防：

\[
LowRes
+
HighRes
\]

同時都被當 canonical owner。

---

# 48. One Active Authoritative Representation

Paper 04 已凍結：

\[
\boxed{
OneActiveAuthoritativeSimulationPathPerStateDimension
}
\]

所以切 resolution 時必須：

```text
old representation authoritative
    ↓ transition
new representation authoritative
```

不能兩邊一起寫。

---

# 49. KEEP — Compiler as Semantic Firewall

現有 Compiler 已經拒絕：

- unknown target；
- illegal state；
- ambiguous transition；
- unreachable path；
- unknown field；
- unsupported behavior。

這個角色應擴大成：

\[
\boxed{
Compiler
=
WorldStructureFirewall
}
\]

未來 Domain/TMS/FDCS contract 也應先 compile-time 驗證。

---

# 50. ADAPT — Compiler Stages

未來可以逐步變成：

```text
Authoring
  ↓
Schema Validation
  ↓
Semantic Resolution
  ↓
Domain Graph Validation
  ↓
Capability Resolution
  ↓
Resolution Policy Validation
  ↓
Causal Contract Validation
  ↓
Runtime Package
```

但每一步必須保持可獨立 test。

---

# 51. KEEP — Unknown Means Fail Closed

現有 Runtime/Compiler 對 unknown fields/guards 都偏 fail-closed。

這與新版：

\[
HonestUnknown
>
FakePrecision
\]

完全一致。

所以：

\[
\boxed{
Unknown
\neq
AutoGuess
}
\]

必須保留。

---

# 52. KEEP — Presentation Is Read/Intent Adapter

現有：

- Terminal；
- Web；
- Studio；
- MCP；

都不應直接寫 StateStore。

AI World Assembly 的 Three.js proof 也延續同樣結構。

因此：

\[
\boxed{
Presentation
\rightarrow
Intent
\rightarrow
ActionIR
}
\]

繼續 KEEP。

---

# 53. DO NOT MERGE — MCP Distributed Runtime Work

repo 中還有大量：

```text
compilableworld_mcp/
```

包含：

- ACL；
- auth；
- audit；
- outbox；
- runtime coordination；
- ownership lease；
- quorum；
- durability；
- OIDC；
- session store。

這些很有價值。

但它們解的是：

\[
RemoteAccess
+
DistributedCoordination
\]

不是：

\[
WorldDomainSimulation
\]

因此：

\[
\boxed{
MCPInfrastructure
\neq
CRDWSWorldCore
}
\]

Paper 07 不把它們塞進 FDCS / UNPNP2 / TMS。

---

# 54. DO NOT MERGE — Agent Memory Kernel

repo 中的 AMK 提供：

- memory ledger；
- clean promotion；
- attribution；
- evidence；
- retrieval；
- runtime EventIR adapter。

這是相鄰能力。

但：

\[
Memory
\neq
WorldTruth
\]

應維持現有 invariant：

> Memory Adapter 只能訂閱 EventIR，不持有 StateStore write path。

---

# 55. ADAPT — Dynamic MSSP Role Observation

歷史 Dynamic MSSP 已提出：

\[
R_d(M)
=
DeclaredRole
\]

\[
R_o(M,t,c)
=
ObservedRole
\]

\[
R_e(M,t,c)
=
EffectiveRole
\]

這對新版 TMS 很重要。

所以 Paper 05 的 TMS contract 未來可加入：

```text
declared_role
observed_metrics
effective_role_candidate
role_confidence
```

但：

\[
ObservedRole
\]

不能自己直接變更 module authority。

---

# 56. Dynamic MSSP and FDCS Are Different

Dynamic MSSP 問：

> 這個 module 現在實際扮演什麼架構角色？

FDCS 問：

> 這個 world domain 現在應算多細？

所以：

\[
\boxed{
ArchitectureRoleDynamics
\neq
SimulationResolutionDynamics
}
\]

但兩者可互相提供 evidence。

例如一個 TMS 長期變成高 criticality，

FDCS 可將它的最低解析度提高。

---

# 57. ADAPT — MSSP/RDR Existing Double Plane

歷史 MSSP×RDR 文件已清楚分：

\[
MSSP
\rightarrow
What/Why/Type/Relation/Constraint
\]

\[
RDR
\rightarrow
Where/When/How/Provider/Resource/Policy
\]

這個雙平面概念應保留。

CRDWS 新版只是把它再 world-specialize：

```text
MSSP
→ world capability semantics

XRDR
→ recursive world capability resolution / dispatch

FDCS
→ current resolution requirement

TMS
→ executable world capability
```

所以：

\[
\boxed{
MSSPXRDRXUNP
=
Evolution
}
\]

不是：

\[
ReplacementOfEverythingBefore
\]

---

# 58. Current Gap — Domain Composition Is Missing

最核心 gap：

現在 module registry 可以知道：

> 有 combat module。

但不能完整回答：

> combat 位於哪個 World Domain？

> 它與 economy / politics / culture 有什麼 causal relation？

> 它目前是 active 還是 dormant？

> 它需要哪個 resolution？

> 它是否因世界歷史而被新建立？

因此 Domain Graph 是第一優先。

---

# 59. Current Gap — Resolution Governance Is Missing

目前 Scheduler 可以跑 action。

但不能表示：

> 這個遠方城市現在只跑 aggregate economy。

> 這個戰爭前線提高到 high resolution。

> 這個人口群從 individual 收回 cohort。

這需要 FDCS layer。

---

# 60. Current Gap — TMS Resolution Family Is Missing

目前 capability implementation 沒有正式：

\[
LowRes/MidRes/HighRes
\]

family contract。

這是第二階段要補的能力。

---

# 61. Current Gap — Structure Evolution Is Only Partially Proven

Entity creation 已經有 transaction proof。

但：

\[
DomainActivation
\]

\[
DomainSplit
\]

\[
RelationCreation
\]

尚沒有 first-class transaction。

所以 Structure Evolution 目前只完成：

\[
EntityStructure
\]

很小的一部分。

---

# 62. Current Gap — Relation Is Not Yet First-Class Runtime Delta

Paper 03 對：

```text
employs
allied_with
owns
funds
member_of
```

等 relation 給了很高地位。

現有 Runtime 有很多 relation-like facts，

但沒有統一：

\[
RelationDelta
\]

因此後續可能需要。

但第一版 CRDWS migration 不必先做。

---

# 63. Current Gap — Domain-level Causal Graph

EventIR 有因果鏈：

```text
causation_id
correlation_id
```

這很好。

但它描述的是：

\[
EventHistoryCausation
\]

而不是：

\[
DomainCausalModel
\]

兩者都需要。

不能混淆。

---

# 64. Current Gap — Aggregate State

現有 Runtime 的 entity/state model 適合 concrete game slice。

大型世界需要：

\[
Aggregate
\]

例如：

```text
population cohort
industry sector
regional market
faction support distribution
```

這需要新的 representation。

---

# 65. Current Gap — Long-Horizon Time Compression

現有 Scheduler 擅長 bounded ticks / actions。

但 CRDWS 還需要：

\[
1\ day
\rightarrow
1\ month
\rightarrow
10\ years
\]

不同 model。

也就是：

\[
MacroTransition
\]

目前尚未成為 general contract。

---

# 66. Do Not Solve All Gaps at Once

如果同時加入：

- Domain Graph；
- FDCS；
- aggregate state；
- UNPNP2；
- multi-rate；
- relation delta；
- domain delta；
- AI generated TMS；
- distributed host；

會失去 discriminative evidence。

所以：

\[
\boxed{
OneNewArchitecturalHypothesisPerPhase
}
\]

---

# 67. Recommended Migration Phase 0 — Freeze Baseline

先鎖：

```text
CompilableWorld exact baseline:
cf37f539e0807499e8b337f80a5f152324c087f2
```

建立：

- source archive；
- tests；
- example compile；
- scenario run；
- entity transaction witness。

目的：

\[
\boxed{
MigrationMustNotDestroyExistingRuntime
}
\]

---

# 68. Phase 1 — Domain Graph Contract Only

新增：

```text
world-domain-graph.v0.1
```

第一個 test world 不需要經濟全部內容。

只需：

```text
world
├─ society
│  └─ settlement
├─ economy
│  └─ local_market
└─ logistics
   └─ supply
```

並建立 cross-domain relations。

此階段：

\[
NoNewRuntimeBehavior
\]

只驗：

- schema；
- compiler；
- graph；
- receipt。

---

# 69. Phase 2 — Existing Module → TMS Projection

挑現有：

```text
movement.core
```

或：

```text
inventory.core
```

做第一個 TMS projection。

證明：

```text
ModuleContract
→ TMSContract
```

不改 module behavior。

---

# 70. Phase 3 — First Domain-bound TMS

挑一個新 world capability：

例如：

```text
economy.local_market.exchange
```

建立真正：

```text
Domain
→ Capability Requirement
→ TMS Binding
→ Action/Event
→ StateDelta
```

這是第一個 CRDWS vertical slice。

---

# 71. Phase 4 — First Cross-Domain Causal Chain

例如：

```text
logistics.supply.disrupted
    ↓
economy.market.shortage
    ↓
economy.market.price_pressure
```

要求：

- Logistics 不直接寫 Economy；
- EventIR；
- Economy-owned StateDelta；
- causation chain；
- ScenarioIR witness。

---

# 72. Phase 5 — FDCS Two-Level Resolution

只做：

```text
summary
detailed
```

兩級。

例如 local market：

summary：

```text
supply_index
demand_index
price_index
```

detailed：

```text
individual inventories
orders
actors
```

證明：

\[
Aggregate(Refine(S))
\approx
S
\]

---

# 73. Phase 6 — Resolution-aware TMS Switch

同一 capability：

```text
economy.market.simulation
```

有：

```text
summary TMS
detailed TMS
```

FDCS 提 plan，

XRDR/MSSP resolve，

Runtime switch。

---

# 74. Phase 7 — Multi-Rate Scheduler

在前面證明後再加入：

```text
market hourly
population daily
culture weekly
```

但保留 single authoritative world ordering。

---

# 75. Phase 8 — Resolution Receipt + Replay

Snapshot 應保存：

- resolution mode；
- representation owner；
- relevant checkpoint。

Replay 必須能重建：

\[
SameResolutionDecision
\]

或直接 replay committed transition。

---

# 76. Phase 9 — First Structure Evolution Above Entity

這時才考慮：

\[
DomainActivation
\]

例如世界由：

```text
barter
```

發展出：

```text
local_market
```

建立 candidate：

\[
DomainDelta
\]

或同等 structure transition contract。

---

# 77. Phase 10 — UNPNP2 Dynamic Classification Adapter

為什麼不是第一階段就上？

因為先要有：

\[
DomainGraph
\]

才能知道 classification expansion 最終落到哪個 executable structure。

UNPNP2 在這一階段負責：

\[
UnknownWorldPhenomenon
\rightarrow
ClassificationCandidate
\]

但 activation 仍需 governance。

---

# 78. Phase 11 — AI Candidate TMS Generation

等 TMS contract 穩定後，

再讓 AWA：

\[
MissingCapability
\rightarrow
Search
\rightarrow
Reuse
\rightarrow
CandidateTMS
\rightarrow
Validate
\]

不能更早。

否則 AI 只會大量生成尚未穩定的 module format。

---

# 79. Phase 12 — Large World Background Simulation

等：

- Domain Graph；
- FDCS；
- summary/detailed transition；
- multi-rate；
- cross-domain causality；

都驗證後，

才開始真正放大：

```text
multiple cities
multiple regions
economy
military
politics
culture
science
...
```

---

# 80. Why Economy Is a Good First New Domain

經濟很適合第一個 CRDWS domain proof，

因為它天然需要：

- aggregate state；
- microstate；
- multi-rate；
- cross-domain causality；
- conservation；
- resolution switch。

而且不像戰鬥那麼容易被現有 game mechanic 掩蓋架構問題。

---

# 81. Alternative First Domain — Logistics

物流甚至更簡單。

例如：

```text
source
route
capacity
shipment
delay
stock
```

容易建立：

\[
Logistics
\rightarrow
Economy
\]

cross-domain event。

所以實作時可先：

\[
Logistics
+
LocalEconomy
\]

形成第一對 Domain。

---

# 82. Political / Culture Should Not Be First Runtime Slice

不是因為不重要。

而是：

- state harder to validate；
- causality ambiguous；
- AI temptation high；
- ground truth harder；
- resolution metric harder。

所以第一輪先用：

\[
Logistics/Economy
\]

建立 infrastructure。

政治／文化之後再接。

---

# 83. Military Can Reuse Existing Action Mechanics

Combat module 已存在。

未來 Military Domain 不等於 Combat module。

Military Domain 可能包括：

```text
recruitment
logistics
command
morale
doctrine
procurement
combat
intelligence
```

所以：

\[
CombatTMS
\subset
MilitaryDomainCapabilities
\]

而不是：

\[
Military=Combat
\]

---

# 84. Science Domain Will Test Structure Evolution

Science 特別適合後期測：

\[
Discovery
\rightarrow
NewTechnology
\rightarrow
NewDomainStructure
\]

所以它是 DomainDelta / UNPNP2 的好 benchmark。

---

# 85. Current World State Machine Must Be Repositioned

本系列名稱原本常說：

\[
DynamicWorldStateMachine
\]

但現在應明確：

現有 StateIR 是：

\[
\boxed{
OneKindOfWorldCapability
}
\]

不是整個 World 本體。

World 變成：

\[
DomainGraph
+
StateRepresentations
+
TMSGraph
+
CausalGraph
+
ResolutionState
+
History
\]

State machines 仍然重要，

但只是其中一種 dynamics representation。

---

# 86. FSM Is Not the Only Dynamic Model

不同 Domain 可以使用：

- FSM；
- differential model；
- graph propagation；
- agent model；
- stochastic model；
- optimization；
- discrete event；
- AI model；
- pure function；
- rule system。

因此：

\[
\boxed{
World
\neq
OneUniversalFSM
}
\]

這正是從舊 Dynamic World State Machine 到 CRDWS 的最大 conceptual migration。

---

# 87. Existing FSM Remains Valuable

所以不是：

\[
FSM
\rightarrow
Delete
\]

而是：

\[
FSM
\rightarrow
OneTMS/OneSubsystemModel
\]

例如：

- quest FSM；
- institution lifecycle FSM；
- disease stage FSM；
- diplomatic relation FSM。

---

# 88. Runtime Package Evolution

未來 Runtime Package 可逐步新增：

```text
domains
domain_relations
tms_bindings
resolution_policies
causal_links
representation_catalog
```

但要維持：

\[
BackwardCompatibility
\]

舊 package 不含新欄位時：

```text
CRDWS features = disabled/not present
```

而不是直接 invalid。

---

# 89. Capability Flags

可以仿 Entity transaction：

```text
requires_kernel:
  - entity_transaction/v0.1
```

未來新增：

```text
domain_graph/v0.1
resolution_runtime/v0.1
multi_rate_scheduler/v0.1
relation_transaction/v0.1
```

都用 capability negotiation。

這是很好的 migration pattern。

---

# 90. Prefer Optional Runtime Extensions

Phase 10 已經證明：

```text
EntityTransactionRuntime(WorldRuntime)
```

可以 additive extension，

而 base WorldRuntime 不變。

未來 CRDWS 也可採：

```text
DomainAwareRuntime
ResolutionAwareRuntime
```

或 capability mixin/adapter，

但不要立刻把 base Kernel 改成巨型 all-feature runtime。

---

# 91. Avoid Inheritance Explosion

雖然 optional Runtime extension 是好 pattern，

但如果變成：

```text
EntityTransactionResolutionDomainMultiRateRuntime
```

就失敗了。

因此長期應偏向：

\[
ComposableKernelCapabilities
\]

而不是無限 subclass。

---

# 92. Proposed Runtime Capability Registry

可以讓 Kernel 宣告：

```text
state_transaction/v1
entity_transaction/v0.1
domain_graph/v0.1
resolution_runtime/v0.1
multi_rate/v0.1
```

TMS 用：

```text
requires_kernel
```

檢查。

---

# 93. Migration Must Remain Test-Driven

每個新 capability：

\[
RED
\rightarrow
GREEN
\rightarrow
Evidence
\]

RED 必須證明：

> 現有 Runtime 的確缺這個 contract。

不能只是：

> Paper 說未來可能需要。

---

# 94. No Speculative Kernel Expansion

例如 Paper 03 提到：

\[
RelationDelta
\]

但如果第一個 domain proof 完全不需要 transactionally create relation，

就：

\[
DEFER
\]

直到有 concrete failing test。

---

# 95. Same for DomainDelta

Paper 03 提出 Domain structure evolution。

但第一個 Domain Graph 可以是 static compiled structure。

只有當世界內事件真的需要：

\[
ActivateNewDomainAtRuntime
\]

才做 DomainDelta。

---

# 96. Same for Full UNPNP2

先接：

\[
ClassificationAdapter
\]

再觀察是否需要：

- dynamic path recomposition；
- deep chart-relative unitization；
- runtime classification mutation。

不要一次搬完整理論進 Kernel。

---

# 97. Keep AI Outside Core Runtime

現有 AGENTS invariant：

> Runtime 無 AI、無網路、無 Web UI 仍能執行基本世界。

這條應升格為 CRDWS invariant：

\[
\boxed{
AIOptionalForCoreWorldExecution
}
\]

AI 可以增強世界，

但不應讓基本世界：

\[
NoModelAPI
\Rightarrow
WorldStopsExisting
\]

---

# 98. AI as Generator / Planner / High-Cost TMS

未來 AI 可以：

- generate candidate TMS；
- refine microstate；
- simulate social reasoning；
- propose domain expansion；
- produce narrative projection。

但仍受：

- budget；
- authority；
- provenance；
- validation；

治理。

---

# 99. AWA Integration Point

AI World Assembly 最適合接在：

```text
Missing Domain Artifact
Missing Capability
Missing TMS
Missing Resolution Adapter
```

之後。

流程：

\[
WorldNeed
\rightarrow
Search
\rightarrow
AWA
\rightarrow
Candidate
\rightarrow
Validate
\rightarrow
PromotionDecision
\]

不是：

\[
Runtime
\rightarrow
LLM
\rightarrow
DirectWrite
\]

---

# 100. SEDB Integration Point

SEDB 可以提供：

- Domain semantic identity；
- field definition；
- provenance；
- classification candidate；
- schema evolution evidence。

Runtime 只讀 semantic contract，

再映射：

\[
SemanticDefinition
\rightarrow
RuntimeRepresentation
\]

不能把兩層混成同一 DB authority。

---

# 101. RDSS Integration Point

RDSS 可在未來提供：

- operator algebra；
- type/effect；
- branch/quotient reasoning；
- state composition formalization。

但 Paper 07 不要求把 RDSS 直接變成 Runtime dependency。

應先：

\[
FormalModel
\rightarrow
TestableInvariant
\]

再決定是否工程化。

---

# 102. Current Migration Architecture

建議總圖：

```text
                 ┌──────────────────────┐
                 │ UNPNP2 Classification│
                 │       Adapter        │
                 └──────────┬───────────┘
                            │ candidate structure
                            ▼
┌────────────┐      ┌───────────────────┐
│    SEDB    │─────▶│  World Domain Graph│
│ semantics  │      │  Active Composition│
└────────────┘      └─────────┬─────────┘
                              │ capability requirements
                              ▼
                    ┌────────────────────┐
                    │ MSSP / TMS Resolver│
                    └─────────┬──────────┘
                              │
                     resolution context
                              ▲
                    ┌─────────┴──────────┐
                    │       FDCS         │
                    │ Resolution Governor│
                    └─────────┬──────────┘
                              │ selected capability
                              ▼
┌──────────────────────────────────────────────────┐
│ Existing CompilableWorld Runtime Kernel          │
│ ActionIR / StateDelta / EntityDelta / EventIR    │
│ StateStore / EventLog / Scheduler / Snapshot     │
└─────────────────────────┬────────────────────────┘
                          │
                          ▼
                  Runtime World State
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
         AWA / AI                Projection/UI
   candidate generation          read + intent
```

---

# 103. The Critical Boundary

這張圖最重要的地方是：

\[
\boxed{
FDCS/UNPNP2/DomainGraph
}
\]

沒有直接取代：

\[
\boxed{
StateStore/ActionIR/EventIR
}
\]

它們是新的 governance/composition plane。

這使 migration 可控。

---

# 104. Migration Anti-Pattern — Rewrite Kernel First

禁止：

```text
新版理論很完整
→ kernel.py 全重寫
→ 再看看測試
```

正確：

```text
找 concrete gap
→ RED
→ minimal capability
→ existing regression
→ evidence
```

---

# 105. Migration Anti-Pattern — Everything Becomes Domain

不是每個資料結構都要叫 Domain。

例如：

- room 是 spatial entity；
- quest 是 gameplay state machine；
- TMS 是 capability；
- presentation 是 projection；
- memory 是 evidence。

不要因為 Domain Graph 新加入就：

\[
Everything
\rightarrow
Domain
\]

---

# 106. Migration Anti-Pattern — Everything Becomes TMS

同樣：

\[
Domain
\neq
TMS
\]

\[
State
\neq
TMS
\]

\[
Asset
\neq
TMS
\]

\[
Event
\neq
TMS
\]

TMS 只代表 executable capability。

---

# 107. Migration Anti-Pattern — FDCS Owns World Rules

FDCS 不能直接：

```text
if war:
   economy.price *= 2
```

那是 Economy capability 的規則。

FDCS 只決定：

> 用哪個 resolution / model。

---

# 108. Migration Anti-Pattern — UNPNP2 Auto-Activates Domains

UNPNP2 找到：

```text
politics/nuclear_deterrence
```

不代表世界已經有核武。

Activation 需要 world evidence / governance。

---

# 109. Migration Anti-Pattern — SEDB Becomes Everything DB

不要把：

```text
semantic
runtime
events
transactions
memory
assets
```

全部塞 SEDB。

SEDB 保留 semantic/schema evolution role。

---

# 110. Migration Anti-Pattern — AWA Becomes Runtime

AWA 可以 orchestration 很多 candidate task，

但：

\[
OrchestrationSuccess
\not\Rightarrow
RuntimeWorldMutation
\]

---

# 111. Migration Anti-Pattern — Dynamic MSSP Auto-Reclassifies Authority

觀察到某 TMS 很重要：

\[
R_e\approx SMS
\]

不代表它自動得到：

```text
more write authority
```

role observation 與 authority promotion 分開。

---

# 112. First Concrete CRDWS Benchmark

Paper 07 建議第一個真正 migration benchmark 不要直接用完整大型世界。

使用：

\[
\boxed{
SettlementSupplyMiniWorld
}
\]

例如：

```text
Domain: logistics.supply
Domain: economy.local_market
Domain: society.settlement
```

Entity：

```text
settlement
warehouse
market
carrier
resource
```

Event：

```text
shipment.delayed
stock.arrived
market.shortage
price.changed
```

---

# 113. Benchmark Goal

第一版只證明：

\[
DomainGraph
\]

\[
\downarrow
\]

\[
TMSBinding
\]

\[
\downarrow
\]

\[
EventIRCrossDomain
\]

\[
\downarrow
\]

\[
OwnedStateDelta
\]

不做 FDCS。

---

# 114. Second Benchmark

加入兩級 resolution：

```text
summary market
detailed market
```

並證明：

\[
Aggregate(HighRes)
=
LowRes
\]

在 bounded tolerance 內。

---

# 115. Third Benchmark

加入：

```text
war / disaster
```

讓 Logistics causal relevance 提升，

FDCS 自動：

\[
Summary
\rightarrow
Detailed
\]

再降回 Summary。

---

# 116. Fourth Benchmark

加入 structure evolution：

```text
barter settlement
        ↓
trade frequency grows
        ↓
candidate local_market domain
        ↓
review/activation
```

才正式測：

\[
WorldChangesWhatTheWorldIs
\]

---

# 117. Compatibility Requirement

每一 Phase 都必須保證舊：

```text
gray_crown
mingyun_zhiyu_peace_city
Alien Lineage external module
Relay Station external module
```

至少其既有 compatible contracts 不被破壞。

新 CRDWS feature 應 opt-in。

---

# 118. Legacy Runtime Packages

舊 package：

\[
NoDomainGraph
\]

應可被解讀為：

```text
legacy composition mode
```

而不是完全不能載入。

---

# 119. Migration Receipt

每次新版 package migration 應產：

```text
source_version
target_version
added_contracts
unchanged_contracts
new_capabilities
compatibility_status
warnings
evidence_hash
```

---

# 120. No Silent Migration

Compiler 不應：

> 自動猜你這個 `system.*` 應該是哪個 Domain。

應輸出：

```text
unmapped
```

並產 migration suggestion。

---

# 121. Human / AI Mapping Review

可以由 AI 建議：

```text
combat.core
→ world.military.combat
```

但這只是：

\[
CandidateBinding
\]

需要 review。

---

# 122. Existing Studio Pattern Can Be Reused

現有 Studio：

```text
import
→ World IR
→ diagnostics
→ mapping suggestion
→ review
→ mapping validation
→ compile
```

這幾乎可以原封不動借給：

```text
legacy module
→ TMS mapping
legacy system
→ Domain mapping
```

所以：

\[
\boxed{
StudioMigrationPattern
=
KEEP
}
\]

---

# 123. Recommended Migration Tool

未來可以新增：

```text
cw-runtime crdws-audit <world/package>
```

輸出：

```text
domains found
unmapped modules
candidate TMS bindings
state ownership
cross-domain writes
resolution readiness
structure-evolution readiness
```

但這是 Paper 07 roadmap，

尚未宣稱已實作。

---

# 124. Migration Readiness Levels

可定義：

```text
Level 0 — Legacy Runtime
Level 1 — Domain Described
Level 2 — TMS Bound
Level 3 — Cross-Domain Causal
Level 4 — Resolution Aware
Level 5 — Multi-Rate
Level 6 — Structure Evolving
Level 7 — AI-Assisted Expansion
```

不是 maturity marketing，

而是 migration checklist。

---

# 125. Level 0

現有：

```text
compilableworld-runtime-mvp
```

其核心大致已超過普通 Level 0，

但尚未有新版 Domain/FDCS contract，

所以在 CRDWS taxonomy 中仍先標：

\[
LegacyCompatibleFoundation
\]

---

# 126. Level 1 — Domain Described

世界能提供：

\[
DomainGraph
\]

但 Runtime behavior 不變。

---

# 127. Level 2 — TMS Bound

所有 active capability 能回答：

> 哪個 TMS 提供？

---

# 128. Level 3 — Cross-Domain Causal

至少兩個 Domain：

\[
D_A
\rightarrow
Event
\rightarrow
D_B
\]

可驗證。

---

# 129. Level 4 — Resolution Aware

至少一個 Domain 可：

\[
Low
\leftrightarrow
High
\]

且 consistency proof 成立。

---

# 130. Level 5 — Multi-Rate

至少兩個 Domain 以不同 rate 運作，

仍可 deterministic replay。

---

# 131. Level 6 — Structure Evolving

世界事件可透過治理流程：

\[
DomainSet_t
\neq
DomainSet_{t+1}
\]

---

# 132. Level 7 — AI-Assisted Expansion

AI 能：

\[
WorldNeed
\rightarrow
CandidateDomain/TMS
\]

但：

\[
AI
\neq
PromotionAuthority
\]

---

# 133. What Is Actually Stable Now

經本次 audit，

以下可以視為近期不應大改的「工程硬核」：

\[
\boxed{
Authoring
\rightarrow
Compiler
\rightarrow
RuntimePackage
}
\]

\[
\boxed{
ActionIR
\rightarrow
ModuleEvaluate
\rightarrow
Delta/Event
\rightarrow
KernelCommit
}
\]

\[
\boxed{
StateOwnership
+
VersionConflict
+
AtomicCommit
}
\]

\[
\boxed{
EventDrivenCrossModuleInteraction
}
\]

\[
\boxed{
Snapshot
+
Replay
+
Evidence
}
\]

---

# 134. What Is Newly Stable Conceptually

Paper 01–05 新凍結的「上層硬核」：

\[
\boxed{
World
=
RecursiveDomainComposition
}
\]

\[
\boxed{
Domain
\neq
TMS
}
\]

\[
\boxed{
FullExistence
\neq
FullResolution
}
\]

\[
\boxed{
WorldEvolution
=
StateEvolution
+
StructureEvolution
}
\]

所以 migration 就是把兩組硬核接起來。

---

# 135. The Bridge

工程底層：

\[
ActionIR/Delta/Event/Commit
\]

上層世界結構：

\[
Domain/UNPNP2/FDCS/TMS
\]

中間需要：

\[
\boxed{
BindingContracts
}
\]

包括：

- Domain → State；
- Domain → Capability；
- Capability → TMS；
- Domain → Resolution Policy；
- Event → Causal Relation；
- Representation → StateStore。

---

# 136. Paper 07 Canonical Migration Equation

\[
\boxed{
CRDWS
=
ExistingCompilableWorldKernel
+
DomainComposition
+
UNPNP2Binding
+
FDCSResolution
+
TMSVNext
+
CrossDomainCausality
+
StructureEvolution
}
\]

這裡的 `+` 是 architecture integration，

不是把所有 code 塞進同一 package。

---

# 137. Implementation Order

本文件建議目前施工順序：

```text
0. Freeze exact existing runtime baseline

1. World Domain Graph contract
2. Domain composition compiler + receipt
3. Existing ModuleContract → TMS compatibility projection
4. One new Domain-bound TMS
5. Cross-domain EventIR causal proof
6. Two-level FDCS resolution state
7. Aggregate ↔ detailed state migration
8. Resolution-aware TMS selection
9. Multi-rate scheduler extension
10. Resolution snapshot/replay
11. Runtime Domain activation proposal/transaction
12. UNPNP2 classification adapter
13. AWA candidate TMS/domain generation
14. Scale to economy/military/politics/culture/science...
```

注意：

\[
UNPNP2
\]

並不是不重要。

它反而太高層，

所以不應在 Domain Graph 尚不存在時先落地成無處可接的 runtime code。

---

# 138. What Not To Implement Yet

目前 DEFER：

- full arbitrary DomainDelta；
- generic RelationDelta；
- recursive dynamic Action Graph；
- parallel Action joins；
- distributed world consensus；
- cross-host ACID；
- full AI autonomous domain promotion；
- arbitrary natural-language world guards；
- unrestricted ontology mutation；
- full eight-dimensional FDCS optimizer；
- universal political/cultural AI simulator。

---

# 139. First Release Target

第一個新版實作版本可以叫：

```text
CRDWS Runtime Migration v0.1
```

只要求：

\[
\boxed{
StaticDomainGraph
+
TMSBinding
+
ExistingKernel
}
\]

這已經足以跨出關鍵一步。

---

# 140. v0.2 Target

再加入：

\[
CrossDomainCausalEvent
\]

---

# 141. v0.3 Target

加入：

\[
TwoLevelResolution
\]

---

# 142. v0.4 Target

加入：

\[
ResolutionAwareTMS
+
MultiRate
\]

---

# 143. v0.5 Target

加入：

\[
FirstRuntimeStructureEvolution
\]

---

# 144. v1.0 Meaning

CRDWS v1.0 不應以：

> 功能很多。

判定。

而應以至少：

1. 多 Domain；
2. Domain Graph；
3. cross-domain causality；
4. multiple TMS；
5. multiple resolutions；
6. multi-rate；
7. structure evolution；
8. snapshot/replay；
9. governed AI candidate expansion；

都至少有一個 executable proof。

---

# 145. Migration Invariants

## MI-1 — Do Not Rewrite Validated Kernel Without Proven Gap

\[
\boxed{
NoGap
\Rightarrow
NoKernelRewrite
}
\]

## MI-2 — New World Concepts Enter Through Contracts

\[
\boxed{
NewConcept
\rightarrow
Schema
\rightarrow
Compiler
\rightarrow
Runtime
}
\]

## MI-3 — Domain Graph Is Additive

\[
\boxed{
DomainGraph
\neq
ReplacementForAllWorldData
}
\]

## MI-4 — Scoped StateIR Is Not Domain Ontology

\[
\boxed{
StateScope
\neq
DomainStructure
}
\]

## MI-5 — Existing Modules Are TMS Ancestors

\[
\boxed{
ExistingModule
\rightarrow
AdaptBeforeRewrite
}
\]

## MI-6 — EventIR Remains Cross-Boundary Transport

\[
\boxed{
CrossDomainInfluence
\rightarrow
Event/Contract
}
\]

## MI-7 — StateStore Remains Runtime Authority

\[
\boxed{
SemanticLayer
\neq
RuntimeStateAuthority
}
\]

## MI-8 — FDCS Does Not Own Domain Rules

\[
\boxed{
ResolutionAuthority
\neq
WorldRuleAuthority
}
\]

## MI-9 — UNPNP2 Does Not Activate World Structure by Itself

\[
\boxed{
Classification
\neq
Activation
}
\]

## MI-10 — AI Remains Optional to Core Execution

\[
\boxed{
NoAI
\Rightarrow
CoreWorldStillRuns
}
\]

## MI-11 — Resolution Transition Must Be Proven

\[
\boxed{
Refine/Aggregate
\Rightarrow
ConsistencyEvidence
}
\]

## MI-12 — New Runtime Capability Is Opt-In

\[
\boxed{
LegacyPackage
\Rightarrow
BackwardCompatibleMode
}
\]

## MI-13 — Structure Evolution Must Be Transactional or Recoverable

\[
\boxed{
NoPartialWorldStructure
}
\]

## MI-14 — One New Architectural Hypothesis Per Phase

\[
\boxed{
EvidenceBeforeExpansion
}
\]

## MI-15 — Integration Does Not Collapse Project Identity

\[
\boxed{
SEDB
\neq
AWA
\neq
CompilableWorld
\neq
FDCS
\neq
UNPNP2
}
\]

---

# 146. Baseline Evidence Notes

本次 migration audit 的已確認 current Runtime facts包括：

### CompilableWorld current exact latest commit

```text
cf37f539e0807499e8b337f80a5f152324c087f2
```

其新增 transaction-safe runtime entity creation。

### Runtime Capability Matrix

2026-08-09 的 capability audit 已列：

- compiler；
- schemas；
- EntityRegistry；
- StateStore；
- ActionIR；
- StateDelta；
- EventIR；
- ModuleContract；
- EventBus；
- EventLog；
- Snapshot；
- Replay；
- Scheduler；
- FunctionIR；
- ScenarioIR；
- Studio；
- AMK；
- MCP integration boundaries。

該 audit 當時記錄 316 tests。

其後 2026-09-09 又新增 Entity Transaction v0.1。

### Scoped StateIR

目前已支援：

```text
world
region
scene
entity
system
```

五種 owner scope，

但文件明確指出 owner scope 是 ownership / visibility，

不是自動地理事件路由。

### Action behavior v0.7

目前是：

```text
bounded static phase DAG
```

不是 generic dynamic recursive graph。

### Entity Transaction v0.1

目前：

```text
create-only
expected_absent=true
governed entity ID
```

不含 remove/despawn/replace。

這些限制都應保留，

直到新 use case 證明需要擴充。

---

# 147. Final Migration Position

在這次新版概念完成後，

最容易犯的錯誤是：

> 「既然我們現在理解的世界更完整，那以前的 Runtime 應該過時了。」

實際 audit 結果恰好相反。

現有 CompilableWorld 最有價值的地方，

正是它已經把許多未來 CRDWS 最難維持的工程原則先做對：

- contract first；
- fail closed；
- authority separation；
- delta commit；
- event causality；
- replay；
- deterministic compilation；
- no hidden UI world rules；
- no AI direct state writes。

因此新版不是對舊版的否定。

新版是在它上面補：

\[
\boxed{
WorldComposition
}
\]

\[
\boxed{
DynamicResolution
}
\]

\[
\boxed{
RecursiveClassification
}
\]

\[
\boxed{
ResolutionAwareCapabilities
}
\]

\[
\boxed{
StructureEvolution
}
\]

---

# 結論

本次 Paper 07 的最終判定可以壓縮為一句話：

\[
\boxed{
KeepTheKernel;
ExpandTheWorld
}
\]

我們不需要重新發明：

- ActionIR；
- StateDelta；
- EventIR；
- atomic commit；
- EventLog；
- Snapshot；
- Replay；
- Compiler；
- ModuleContract；

真正需要做的是：

\[
\boxed{
ExistingTransactionalWorldRuntime
\rightarrow
ComposableRecursiveDynamicWorldRuntime
}
\]

而最安全的施工方式是：

\[
\boxed{
Contracts
\rightarrow
DomainGraph
\rightarrow
TMSBindings
\rightarrow
CrossDomainCausality
\rightarrow
FDCSResolution
\rightarrow
MultiRate
\rightarrow
StructureEvolution
\rightarrow
AIExpansion
}
\]

因此新版 MSSPXRDRXUNP / UNPNP2 並不是「取代 CompilableWorld」。

更準確的是：

\[
\boxed{
CompilableWorld
=
ValidatedRuntimeKernelFoundation
}
\]

而：

\[
\boxed{
CRDWS
=
TheWorldCompositionAndSimulationArchitectureThatNowGrowsAroundIt
}
\]

最後，

從舊的 Dynamic World State Machine 到現在真正的轉變不是：

\[
FSM_v1
\rightarrow
FSM_v2
\]

而是：

\[
\boxed{
StateMachineWorld
\rightarrow
WorldOfComposableDynamicSystems
}
\]

這就是下一階段真正的工程起點。

---

**End of Paper 07**
