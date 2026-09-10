# Paper 05 — TMS World Capability Module Specification

**系列：Dynamic World Simulator Canonical Series v1**  
**文件定位：TMS Capability Contract / Executable World Module Specification**  
**狀態：Canonical Baseline**  
**版本：v1.0**  
**日期：2026-09-10**

---

## 摘要

Paper 01 已將新版 Dynamic World Simulator 定義為：

\[
\boxed{
Composable\ Recursive\ Dynamic\ World\ Simulator
}
\]

Paper 02 將 MSSPXRDRXUNP / UNPNP2 的架構責任拆開。

Paper 03 定義：

\[
\boxed{
WorldComposition
=
RecursiveDomainGraph
}
\]

Paper 04 進一步建立：

\[
\boxed{
PotentiallyInfiniteWorldStructure
+
FiniteActiveComputation
}
\]

並將 FDCS 定位為：

\[
\boxed{
DynamicClassificationAndSimulationResolutionGovernor
}
\]

Paper 05 專門回答下一個不可迴避的問題：

> **當世界需要「經濟、軍事、政治、文化、人際、科學、物流、法律、教育、醫療……」等大量功能時，這些功能到底應該以什麼形式存在？**

本文件將 TMS 定義為：

\[
\boxed{
TMS
=
ExecutableWorldCapabilityModule
}
\]

TMS 不是 Domain。

TMS 不是 Renderer。

TMS 不是 AI Provider。

TMS 不是一個大型「經濟系統」。

TMS 是一個具有明確能力邊界、讀寫權限、事件介面、時間尺度、解析度支援、依賴、近似誤差與治理資訊的**可執行世界能力模組**。

其 canonical responsibility model 為：

\[
\boxed{
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
}
\]

本文件的核心命題是：

\[
\boxed{
DomainDescribesWhatTheWorldContains
}
\]

而：

\[
\boxed{
TMSDescribesWhatTheWorldCanDo
}
\]

因此：

\[
\boxed{
Domain
\neq
TMS
}
\]

---

# 1. 為什麼 TMS 必須獨立成正式 contract

如果沒有正式 TMS contract，世界功能很容易退化成：

```text
EconomySystem
MilitarySystem
PoliticsSystem
CultureSystem
ScienceSystem
```

接著每個 System 不斷擴張：

```text
EconomySystem
├─ trade
├─ price
├─ production
├─ labor
├─ banking
├─ tax
├─ logistics
├─ contract
├─ credit
├─ insurance
└─ ...
```

最後變成：

\[
\boxed{
GodModule
}
\]

這會帶來：

- 權限邊界不清；
- 無法局部替換；
- 無法 resolution switching；
- 無法局部驗證；
- 無法重用；
- 無法安全讓 AI 生成能力；
- 難以做跨 Domain composition；
- 難以知道某一 state 到底誰能寫；
- 難以 replay；
- 難以比較不同模型。

因此，本系列採用：

\[
\boxed{
LargeWorldFunctionality
=
CompositionOfBoundedCapabilities
}
\]

---

# 2. TMS 的最小概念

一個 TMS 應回答：

1. 我是誰？
2. 我提供什麼能力？
3. 我服務哪些 Domain？
4. 我需要讀什麼？
5. 我可以寫什麼？
6. 我接收什麼 input？
7. 我產生什麼 output / event？
8. 我在哪個時間尺度運作？
9. 我依賴誰？
10. 我支援哪些 resolution？
11. 我是 exact 還是 approximate？
12. 我的 authority 到哪裡？
13. 我是否 deterministic？
14. 我的版本與 provenance 是什麼？

因此：

\[
\boxed{
Capability
\neq
ImplementationNameOnly
}
\]

---

# 3. Canonical TMS Identity

每一個 TMS 應有穩定 identity。

例如：

```text
tms.economy.market.price_discovery
tms.economy.labor.employment
tms.military.logistics.supply
tms.politics.faction.legitimacy
tms.social.interpersonal.trust
tms.science.research.discovery
```

Identity 不應綁死：

- provider；
- model；
- programming language；
- deployment location。

例如：

```text
tms.social.negotiation
```

可以有：

```text
implementation.rule.v1
implementation.llm.v3
implementation.hybrid.v2
```

所以：

\[
\boxed{
CapabilityIdentity
\neq
ProviderIdentity
}
\]

---

# 4. Version

TMS 必須版本化。

例如：

```text
id: tms.economy.market.price_discovery
version: 2.1.0
```

因為世界 replay、save、migration、A/B model 比較，都需要知道：

\[
WhichImplementationVersionRan?
\]

所以：

\[
\boxed{
TMSExecution
\Rightarrow
VersionEvidence
}
\]

---

# 5. Capability

Capability 描述：

> 這個 TMS 能做什麼。

例如：

```text
capability:
  id: economy.market.price_discovery
  mode: state_transition
```

或：

```text
capability:
  id: science.research.discovery
  mode: event_producer
```

Capability 不應用自然語言描述就結束。

長期應具備可機器匹配的 identity。

---

# 6. Domain Bindings

TMS 可以綁定一個或多個 Domain。

例如：

```text
domain_bindings:
  - world.economy.market
```

也可能：

```text
domain_bindings:
  - world.military.logistics
  - world.economy.transport
```

因此：

\[
\boxed{
TMSDomainBinding
=
ManyToMany
}
\]

但：

\[
Binding
\neq
Authority
\]

被某 Domain 使用，不代表 TMS 可以任意修改該 Domain 全部 state。

---

# 7. Inputs

Inputs 是 TMS 明確接收的 invocation payload。

例如：

```text
inputs:
  - actor_id
  - market_id
  - commodity_id
  - quantity
```

Inputs 應和：

\[
Reads
\]

分開。

因為 caller 傳入的 input 與 TMS 從 world state 讀取的資料不是同一類 authority。

---

# 8. Reads

Reads 定義 TMS 可觀察哪些 canonical state projection。

例如：

```text
reads:
  - economy.market.inventory
  - economy.market.demand
  - economy.market.supply
```

Reads 不代表 TMS 擁有這些 state。

因此：

\[
\boxed{
ReadPermission
\neq
WriteAuthority
}
\]

---

# 9. Writes

Writes 是最重要的 contract 之一。

例如：

```text
writes:
  - economy.market.price
  - economy.market.volume
```

如果 TMS 沒宣告：

```text
economy.household.income
```

則不能寫。

因此：

\[
\boxed{
WriteScope
=
ExplicitAllowlist
}
\]

而不是：

\[
EverythingNotForbiddenIsAllowed
\]

---

# 10. One Canonical Owner Per State Dimension

Paper 03 已凍結：

\[
\boxed{
OneCanonicalOwnerPerStateDimension
}
\]

TMS contract 必須支援這一原則。

例如：

```text
economy.labor.workforce
```

可以由：

```text
tms.economy.labor.workforce_transition
```

擁有 canonical transition authority。

Military 不應直接寫 workforce。

Military 應發：

```text
military.mobilization_started
```

再由 Economy 自己的 TMS 消費。

---

# 11. Cross-Domain Influence

因此：

\[
\boxed{
CrossDomainInfluence
\neq
CrossDomainDirectWrite
}
\]

標準模式應偏向：

\[
TMS_A
\rightarrow
Event
\rightarrow
TMS_B
\rightarrow
OwnedStateTransition
\]

這能避免 double counting。

---

# 12. Events

TMS 可以：

- consume events；
- emit events。

例如：

```text
consumes:
  - military.mobilization_started

emits:
  - economy.labor.shortage
```

事件應有：

- identity；
- version；
- source；
- timestamp；
- world scope；
- provenance。

---

# 13. Event Is Not State

Event：

\[
E_t
\]

表示發生某件事。

State：

\[
S_t
\]

表示世界目前是什麼樣子。

因此：

\[
\boxed{
Event
\neq
State
}
\]

不能把 event log 當成 state store，也不能只改 state 而完全沒有事件證據。

---

# 14. Operators

Operators 描述 TMS 提供的可調用行為。

例如：

```text
operators:
  - quote_price
  - settle_trade
```

或：

```text
operators:
  - recruit
  - demobilize
```

Operator 應與 capability identity 對齊。

---

# 15. Constraints

TMS 必須宣告自己需要遵守哪些 constraints。

例如：

```text
constraints:
  - inventory_non_negative
  - money_conservation
```

或：

```text
constraints:
  - entity_must_exist
  - actor_must_have_authority
```

Constraint 可來自：

- Domain；
- Runtime；
- Law；
- Safety；
- Scenario；
- World policy。

---

# 16. Conservation Constraints

某些 TMS 特別需要 conservation：

\[
Money_{before}+Flow
=
Money_{after}
\]

\[
Population_{before}
=
Population_{after}
+
Births
-
Deaths
+
Migration
\]

因此：

\[
\boxed{
TMS
\Rightarrow
ConservationWitness
}
\]

在適用時應是可驗證的。

---

# 17. Timescale

每個 TMS 必須描述其 temporal behavior。

例如：

```text
timescale:
  mode: event_driven
```

或：

```text
timescale:
  mode: scheduled
  interval: 1 day
```

或：

```text
timescale:
  mode: tick
  preferred_frequency_hz: 20
```

---

# 18. Multi-Rate TMS

不同 TMS 本來就可以：

\[
\tau_i
\neq
\tau_j
\]

例如：

```text
combat.damage_resolution        milliseconds
economy.market.daily_summary    day
politics.election_cycle         month/year
culture.norm_diffusion          week/month
```

因此：

\[
\boxed{
TMS
\neq
GlobalTickSlave
}
\]

---

# 19. Event-Driven TMS

若沒有事件：

\[
NoEvent
\Rightarrow
NoExecution
\]

可以是正常模式。

例如：

```text
law.contract.enforcement
```

不需要每秒跑一次。

---

# 20. Scheduled TMS

例如：

```text
economy.payroll.monthly
government.tax.quarterly
politics.election.periodic
```

應由 scheduler 觸發。

---

# 21. Lazy TMS

某些 capability 可以被 query 時才計算。

例如：

```text
route_cost
risk_estimate
aggregate_statistics
```

因此：

\[
\boxed{
CapabilityExists
\neq
CapabilityRunsContinuously
}
\]

---

# 22. Dependencies

TMS 可以宣告：

```text
dependencies:
  required:
    - capability.logistics.route
  optional:
    - capability.weather.forecast
```

Dependency 應以：

\[
Capability
\]

為主，

而不是綁死特定 implementation。

---

# 23. Capability Dependency vs Module Dependency

較差：

```text
depends_on:
  - tms.routing.v1
```

較好：

```text
requires_capability:
  - logistics.route_resolution
```

然後 MSSP resolver 再決定：

\[
Capability
\rightarrow
Implementation
\]

這讓替換成：

```text
routing.v2
```

不需要改所有 consumer。

---

# 24. Required / Optional Dependencies

Required 缺失：

\[
\Rightarrow
Block
\]

Optional 缺失：

\[
\Rightarrow
DegradedMode
\]

但 degraded behavior 必須明確。

---

# 25. Circular Dependency

TMS dependency graph 可能形成 cycle。

例如：

```text
price -> production -> labor -> consumption -> price
```

這在世界因果上可能合理。

但 module initialization dependency 不一定能接受 cycle。

因此必須區分：

\[
RuntimeCausalCycle
\]

與：

\[
InitializationDependencyCycle
\]

---

# 26. Resolution Support

Paper 04 已建立多維解析度。

TMS 必須宣告自己支援什麼 resolution。

例如：

```text
resolution_support:
  class: market
  state: aggregate
  time: daily
  agent: cohort
```

另一個 TMS：

```text
resolution_support:
  class: market.orderbook
  state: detailed
  time: subsecond
  agent: individual
```

---

# 27. Resolution-Specific Implementations

同一 capability 可以有：

```text
tms.market.price.lowres
tms.market.price.midres
tms.market.price.highres
```

它們可以共享：

\[
CapabilityIdentity
\]

但 implementation 不同。

因此：

\[
\boxed{
Capability
\rightarrow
MultipleResolutionImplementations
}
\]

---

# 28. Resolution Transition

當 FDCS：

\[
R_L
\rightarrow
R_H
\]

MSSP/XRDR 可以：

\[
TMS_L
\rightarrow
TMS_H
\]

但 state migration 必須有明確 contract。

---

# 29. State Migration Contract

Resolution switch 可以需要：

```text
migration:
  from: aggregate
  to: detailed
  function: refine
```

或：

```text
migration:
  from: detailed
  to: aggregate
  function: summarize
```

不能直接：

\[
ReplaceModel
\]

而不處理 state。

---

# 30. Approximation Contract

低解析 TMS 很可能是 approximation。

因此可以宣告：

```text
approximation:
  mode: bounded
  metric: price_index
  expected_error: 0.03
  valid_horizon: 30d
```

也可以：

```text
approximation:
  mode: exact
```

---

# 31. Approximation Is First-Class

近似不是「品質比較差」而已。

它是一種正式模型屬性。

所以：

\[
\boxed{
Approximate
\neq
Invalid
}
\]

只要：

\[
ErrorWithinDeclaredBound
\]

就可以是有效模型。

---

# 32. Error Bound

可表達：

\[
|\epsilon|
\le
\epsilon_{max}
\]

若 Runtime 觀察到：

\[
|\epsilon|
>
\epsilon_{max}
\]

則可以：

\[
FDCSResolution\uparrow
\]

或換 TMS。

---

# 33. Confidence

TMS 也可以回傳：

\[
Confidence
\]

例如：

```text
result:
  value: 0.72
  confidence: 0.81
```

尤其適用：

- AI；
- statistical model；
- prediction；
- reconstruction。

---

# 34. Authority

每個 TMS 必須有 authority boundary。

例如：

```text
authority:
  mode: runtime_transition
  world_scope: current
  write_scope:
    - economy.market.price
```

或：

```text
authority:
  mode: proposal_only
```

AI-generated TMS 初期應傾向：

\[
ProposalOnly
\]

---

# 35. Authority Modes

概念上可以有：

```text
read_only
proposal_only
simulation_only
runtime_transition
structure_proposal
```

但 Paper 05 不凍結最終 enum。

重要的是：

\[
\boxed{
AuthorityMustBeExplicit
}
\]

---

# 36. Canonical Write Is Not a Normal TMS Right

TMS 不應因為「跑成功」就自動具有 canonical source 修改權。

因此：

\[
\boxed{
RuntimeTransitionAuthority
\neq
CanonicalContentAuthority
}
\]

尤其：

- semantic database；
- world ontology；
- module registry；

不應被普通 Runtime TMS 任意改寫。

---

# 37. Structure Mutation Authority

未來某些 TMS 可能提出：

\[
DomainDelta
\]

例如新制度形成。

但預設應該是：

\[
StructureProposal
\]

而不是直接：

\[
CanonicalStructureMutation
\]

---

# 38. Side Effects

Side effect 必須明確。

例如：

- network；
- filesystem；
- external API；
- database；
- model call；
- random source。

這些都可能影響 replay 與 determinism。

因此：

\[
\boxed{
SideEffects
\Rightarrow
Declared
}
\]

---

# 39. Pure vs Impure TMS

Pure：

\[
Output
=
F(Input,ReadState)
\]

無外部 side effect。

Impure：

可能：

- 呼叫 API；
- 寫 external system；
- 使用 wall-clock；
- 呼叫 model。

Pure TMS 更適合 replay 與 testing。

Impure TMS 需要更多 evidence。

---

# 40. Determinism

TMS 應宣告：

```text
determinism:
  deterministic: true
```

或：

```text
determinism:
  deterministic: false
  seed_required: true
```

---

# 41. Randomness

若使用 randomness：

\[
Randomness
\Rightarrow
Seed
+
AlgorithmVersion
\]

否則 replay 不可控。

---

# 42. AI TMS

LLM / Agent 可以是一種 TMS implementation。

例如：

```text
tms.politics.negotiation.ai
tms.social.dialogue.ai
tms.science.hypothesis.ai
```

但：

\[
\boxed{
AIModel
\neq
WorldRuntime
}
\]

它只是 capability provider。

---

# 43. Provider Separation

TMS capability 不應綁死：

```text
OpenAI
Anthropic
Gemini
LocalModel
```

而應：

\[
Capability
\rightarrow
ProviderBinding
\]

provider 可替換。

因此：

\[
\boxed{
ProviderIdentity
\neq
WorldSemanticIdentity
}
\]

---

# 44. Provider Routing

某 capability 可以有：

```text
provider_policy:
  preferred: local
  fallback: cloud
```

但 provider routing 應屬 deployment / execution policy，

不應污染 world semantics。

---

# 45. AI Output Is Candidate

AI TMS 若產生：

- 新人物；
- 新制度；
- 新文化；
- 新 scientific hypothesis；

應先標記：

\[
Candidate
\]

除非它只是已授權的 runtime behavior。

---

# 46. TMS Lifecycle

一個 TMS 可經過：

\[
Discover
\]

\[
Candidate
\]

\[
Validate
\]

\[
Register
\]

\[
Activate
\]

\[
Execute
\]

\[
Observe
\]

\[
Upgrade
\]

\[
Deprecate
\]

\[
Retire
\]

---

# 47. Discover

當 world need 出現：

\[
MissingCapability
\]

首先：

\[
SearchExistingCapability
\]

不能直接 generate。

---

# 48. Candidate

若搜尋不到：

\[
GenerateCandidateTMS
\]

Candidate 必須與 canonical registry 分開。

---

# 49. Validate

Validation 至少可能包括：

- schema；
- unit test；
- property test；
- authority scan；
- deterministic test；
- conservation test；
- integration test；
- resolution compatibility；
- performance budget；
- replay witness。

---

# 50. Register

只有 validated candidate 才有資格：

\[
Register
\]

但：

\[
Validated
\neq
AutomaticallyRegistered
\]

還需要 promotion authority。

---

# 51. Activate

Registered TMS 也不等於每個 world 都 active。

World-specific composition 決定：

\[
ActiveTMS(World_i)
\]

---

# 52. Execute

每次 execute 應有：

- module identity；
- version；
- input；
- read snapshot/version；
- output；
- deltas；
- events；
- evidence；
- duration；
- cost。

---

# 53. Observe

Runtime 應監控：

- failures；
- latency；
- error bound；
- drift；
- conflict；
- replay mismatch；
- resource use。

---

# 54. Upgrade

新版本：

\[
TMS_v1
\rightarrow
TMS_v2
\]

不應直接 hot swap。

要檢查：

- state compatibility；
- dependency compatibility；
- event compatibility；
- output contract；
- resolution support。

---

# 55. Deprecate

Deprecated 不代表刪除。

舊 save/replay 可能仍需：

\[
TMS_v1
\]

因此版本 artifact 應可保留。

---

# 56. Capability Registry

MSSP 可以維護：

\[
CapabilityRegistry
\]

例如：

```text
capability: economy.market.price_discovery
implementations:
  - aggregate.v1
  - orderbook.v2
```

但 registry 不等於 active world composition。

---

# 57. Search Before Generate

Canonical route：

\[
\boxed{
MissingCapability
\rightarrow
SearchRegistry
\rightarrow
Reuse
\rightarrow
Compose
\rightarrow
Adapt
\rightarrow
GenerateCandidate
}
\]

不能：

\[
MissingCapability
\rightarrow
Generate
\]

當成預設。

---

# 58. Reuse

若已有：

```text
tms.routing.shortest_path
```

Military 與 Economy 都可以重用。

但它們各自 state authority 分開。

---

# 59. Compose

有時缺少的 capability 可以由多個 TMS 組成。

例如：

\[
MilitarySupply
=
RoutePlanning
+
Inventory
+
TransportCapacity
+
RiskAssessment
\]

因此：

\[
\boxed{
Capability
=
Composable
}
\]

---

# 60. Composite TMS

可以存在：

\[
CompositeTMS
\]

但它不應把 child authority 無限制合併。

Composite 需要顯式：

- child list；
- ordering；
- dataflow；
- write claims；
- failure policy。

---

# 61. Orchestration vs TMS

AWA Phase 12 類型的 multi-task orchestration 不應直接等同於 TMS。

Orchestrator 協調：

\[
ManyTasks
\]

TMS 提供：

\[
WorldCapability
\]

兩者角色不同。

---

# 62. Failure Semantics

TMS 失敗不能留下 half transition。

如果一次 execution 同時產生：

- StateDelta；
- EntityDelta；
- Event；

應：

\[
\boxed{
AllCommit
\lor
NothingCommit
}
\]

在 Runtime 支援範圍內。

---

# 63. Retry

Retry 不應造成：

\[
DuplicateEffect
\]

因此 TMS 若可重試，應支援：

- idempotency；
- write token；
- expected version；
- operation identity。

---

# 64. Idempotency

例如：

```text
pay_salary(employee, period=2026-09)
```

retry 不應重複付兩次。

因此：

\[
\boxed{
RetryableTMS
\Rightarrow
IdempotencyContract
}
\]

---

# 65. Version Conflict

若 state 已被修改：

\[
ExpectedVersion
\neq
ActualVersion
\]

TMS 應：

\[
Fail
\]

或重新 evaluate。

不能靜默 overwrite。

---

# 66. Conflict Is Semantic

Version conflict 不是單純 technical exception。

它表示：

\[
PreconditionNoLongerTrue
\]

因此上層應重新決策。

---

# 67. Read Snapshot

TMS evaluation 應知道自己基於哪個 snapshot。

例如：

```text
read_version:
  market: 1042
```

commit 時驗證。

---

# 68. StateDelta

較理想模式：

\[
TMS
\rightarrow
StateDelta
\]

而不是直接：

\[
TMS
\rightarrow
StateStore.write()
\]

這讓 Runtime 可以：

- validate；
- conflict check；
- rollback；
- log。

---

# 69. EntityDelta

若 TMS 需要 create entity：

\[
EntityDelta(create)
\]

應走 transaction boundary。

不能：

```python
registry.add(...)
```

藏在 module 中。

---

# 70. RelationDelta

未來 relation creation/deletion 也應同樣 first-class。

例如：

```text
company employs worker
country allies country
```

應可 transactionally commit。

---

# 71. DomainDelta

若 TMS 提議世界結構變化：

\[
DomainDelta
\]

預設是：

\[
CandidateStructureMutation
\]

需要更高 authority。

---

# 72. EventIR / Event Evidence

每個重要 transition 應產生：

\[
EventEvidence
\]

讓世界 history 可追蹤。

---

# 73. TMS Output Categories

可以概念分：

\[
StateTransition
\]

\[
EntityTransition
\]

\[
RelationTransition
\]

\[
Event
\]

\[
Projection
\]

\[
Proposal
\]

\[
Metric
\]

不應全部塞成 arbitrary JSON。

---

# 74. Projection-Only TMS

有些 capability 只做 observation projection。

例如：

```text
tms.economy.dashboard.summary
```

它應：

\[
ReadOnly
\]

---

# 75. Proposal-Only TMS

例如：

```text
tms.science.hypothesis.generator
```

輸出：

\[
Proposal
\]

不能直接修改 canonical science truth。

---

# 76. Simulation-Only TMS

某些 TMS 可以在 sandbox world branch 中模擬。

結果不自動 merge 回 canonical world。

---

# 77. TMS Test Classes

最低建議：

```text
ContractTest
UnitTest
PropertyTest
IntegrationTest
AuthorityTest
ReplayTest
ResolutionTest
FailureTest
```

---

# 78. Contract Test

驗：

- required fields；
- no unknown forbidden fields；
- capability identity；
- version；
- writes。

---

# 79. Property Test

例如：

\[
Inventory\ge0
\]

\[
MoneyConserved
\]

\[
Probability\in[0,1]
\]

---

# 80. Authority Test

故意要求 TMS 寫未授權 state。

預期：

\[
Blocked
\]

---

# 81. Replay Test

相同：

- input；
- snapshot；
- seed；
- version；

應產：

\[
SameResult
\]

在 deterministic TMS 中。

---

# 82. Resolution Test

Low-res 與 high-res TMS 應在 aggregate level 一致。

例如：

\[
Aggregate(HighResOutput)
\approx
LowResOutput
\]

---

# 83. Failure Test

故意在 durable commit 中失敗。

確認：

\[
NoPartialWorldMutation
\]

---

# 84. Performance Test

TMS 應提供：

- latency；
- memory；
- CPU/GPU；
- token；
- API cost；

讓 FDCS 做 budget allocation。

---

# 85. Capability Cost Model

概念：

\[
Cost(TMS,R)
=
(
CPU,
GPU,
RAM,
IO,
Latency,
Tokens,
Money
)
\]

---

# 86. Quality Model

也可：

\[
Quality(TMS,R)
=
(
Accuracy,
Fidelity,
Stability,
Confidence
)
\]

FDCS/MSSP 可在：

\[
Quality/Cost
\]

間選擇。

---

# 87. TMS Selection

當多個 implementation 可提供同 capability：

\[
\{M_1,M_2,\dots,M_n\}
\]

resolver 可以依：

- world policy；
- resolution；
- budget；
- deterministic requirement；
- platform；
- safety；
- latency；

選擇。

---

# 88. Selection Is Not Semantic Truth

選了：

```text
provider.model.A
```

不代表世界 ontology 變了。

所以：

\[
\boxed{
ExecutionChoice
\neq
WorldSemanticMutation
}
\]

---

# 89. Hot Swap

若兩個 TMS contract-compatible，

可以支援 hot swap。

但：

\[
HotSwap
\]

仍需：

- state compatibility；
- transition boundary；
- version receipt。

---

# 90. Shadow Execution

可以讓：

\[
TMS_A
\]

作 authoritative，

同時：

\[
TMS_B
\]

shadow run，

比較結果。

這對 AI / statistical model 特別有用。

---

# 91. Twin Validation

兩個 implementation 可獨立跑：

\[
M_A(x)
\]

\[
M_B(x)
\]

比較：

\[
Distance(M_A,M_B)
\]

若差異過大，觸發 review。

---

# 92. TMS Provenance

每個 TMS 應可追：

- author；
- generated_by；
- source；
- training/derivation notes；
- tests；
- validation；
- promotion；
- version lineage。

---

# 93. AI-Generated TMS Provenance

若 AI 生成：

```text
generated_by:
  system: ...
  model: ...
  prompt_hash: ...
  source_refs: ...
```

但 provider metadata 不應污染 capability identity。

---

# 94. Security Boundary

TMS loader 必須假設：

\[
Module
\neq
TrustedByDefault
\]

特別是：

- AI generated；
- external marketplace；
- third-party。

---

# 95. Sandboxing

高風險 TMS 可以：

- process isolation；
- capability sandbox；
- filesystem deny；
- network deny；
- CPU/time budget；
- memory cap。

---

# 96. Network Capability

TMS 若需要 network：

```text
network:
  allowed_hosts:
    - ...
```

不應默認全網可訪問。

---

# 97. Filesystem Capability

類似：

```text
filesystem:
  read:
    - ...
  write:
    - ...
```

---

# 98. Secret Access

TMS 不應直接拿所有 secret。

只拿其 capability 需要的 credential scope。

---

# 99. TMS and World Authority

世界 Runtime 可以信任：

\[
ValidatedTMS
\]

執行已授權 transition。

但這仍不代表 TMS 可以改：

- registry；
- schema；
- ontology；
- canonical source；

除非有獨立 authority。

---

# 100. Minimal TMS Contract Example

```yaml
id: tms.economy.market.price_discovery
version: 1.0.0

capability:
  id: economy.market.price_discovery

domain_bindings:
  - world.economy.market

inputs:
  - market_id
  - commodity_id

reads:
  - economy.market.supply
  - economy.market.demand
  - economy.market.inventory

writes:
  - economy.market.price

consumes:
  - economy.market.order_changed

emits:
  - economy.market.price_changed

timescale:
  mode: event_driven

dependencies:
  required: []

resolution_support:
  state:
    - aggregate
    - detailed
  time:
    - event_driven

approximation:
  mode: bounded
  expected_error: 0.02

authority:
  mode: runtime_transition

determinism:
  deterministic: true

provenance:
  source: canonical
```

---

# 101. AI TMS Contract Example

```yaml
id: tms.social.negotiation.ai
version: 0.3.0

capability:
  id: social.negotiation

domain_bindings:
  - world.social.interpersonal
  - world.politics.diplomacy

reads:
  - social.relationship.trust
  - actor.goal
  - actor.memory.summary

writes: []

emits:
  - social.negotiation.proposal

resolution_support:
  agent:
    - individual

approximation:
  mode: stochastic
  confidence_required: true

authority:
  mode: proposal_only

determinism:
  deterministic: false
  seed_required: false
```

重點是：

\[
writes=[]
\]

所以 AI 可以提案，

不能自己修改 relationship truth。

---

# 102. Low-Resolution TMS Example

```yaml
id: tms.demography.population.aggregate
version: 1.0.0

capability:
  id: demography.population_transition

resolution_support:
  state:
    - aggregate
  time:
    - monthly

approximation:
  mode: bounded
  expected_error: 0.01

writes:
  - demography.population.total
  - demography.population.age_distribution
```

---

# 103. High-Resolution TMS Example

```yaml
id: tms.demography.population.individual
version: 1.0.0

capability:
  id: demography.population_transition

resolution_support:
  state:
    - detailed
  agent:
    - individual

writes:
  - demography.person.life_state
```

兩者共享 capability family，

但 state representation 不同。

---

# 104. TMS Family

可以定義：

\[
TMSFamily(C)
=
\{M_1,M_2,\dots\}
\]

例如：

```text
capability: demography.population_transition
├─ aggregate
├─ cohort
└─ individual
```

FDCS/XRDR 按 resolution 選擇。

---

# 105. TMS and Domain Split

當 Domain：

\[
D
\rightarrow
D_1+D_2
\]

TMS binding 也可能需要：

\[
Rebind
\]

不能假設舊 module 自動適配。

---

# 106. TMS and Domain Merge

反之：

\[
D_1+D_2
\rightarrow
D
\]

也可能改用 aggregate TMS。

---

# 107. Capability Gap

若 Domain activation 需要：

\[
C
\]

但 registry 找不到：

\[
MissingCapability(C)
\]

世界可以：

\[
BlockActivation
\]

或：

\[
ActivateInDegradedMode
\]

但不能假裝 capability 已存在。

---

# 108. Degraded Mode

若 optional capability 缺失：

```text
status: degraded
```

應明確記錄。

例如：

市場可以沒有 weather forecast，

但 prediction confidence 降低。

---

# 109. Capability Promotion

AI 生成 candidate TMS：

\[
Candidate
\]

通過 validation 後：

\[
ValidatedCandidate
\]

仍不是 active。

需要：

\[
PromotionAuthority
\]

才可：

\[
Registered
\]

---

# 110. Validation vs Registration vs Activation

因此：

\[
\boxed{
Validation
\neq
Registration
\neq
Activation
}
\]

這三層不能混。

---

# 111. TMS Registry Authority

Registry 本身必須受治理。

普通 TMS 不應：

```text
register_module(self)
```

直接把自己寫進 canonical registry。

---

# 112. Runtime Module Load

Runtime 可以從已批准 registry：

\[
Load(TMS)
\]

但 load receipt 應包括：

- identity；
- version；
- hash；
- dependencies；
- authority；
- world scope。

---

# 113. TMS Hash

可執行 artifact 應有：

\[
SHA256
\]

或其他 content identity。

版本號相同但 bytes 不同應被視為問題。

---

# 114. Reproducible Module Artifact

理想：

\[
SameSource
\rightarrow
SameBuildArtifact
\]

在可重現 build 下。

---

# 115. TMS Runtime Receipt

每次 activation 可留下：

```text
module_id
version
artifact_hash
world_scope
resolution_mode
dependency_bindings
authority
activated_at
```

---

# 116. TMS Execution Receipt

每次重要 transition 可包含：

```text
module_id
version
action_id
input_hash
read_versions
output_hash
delta_hash
event_ids
duration
cost
result
```

---

# 117. Observability

TMS 必須可觀測。

最低：

- invocation count；
- failure count；
- p50/p95 latency；
- conflict count；
- retry count；
- cost；
- approximation error；
- resolution usage。

---

# 118. Failure Isolation

一個 TMS 崩潰：

\[
\not\Rightarrow
WholeWorldCrash
\]

理想 Runtime 應：

- isolate；
- rollback；
- degrade；
- retry；
- fallback。

---

# 119. Fallback TMS

Capability family 可以有：

```text
primary
fallback
```

例如 AI negotiation 掛掉時：

\[
AIModel
\rightarrow
RuleBasedFallback
\]

但行為品質下降要標記。

---

# 120. Safety Critical TMS

高風險 capability 可以要求：

- deterministic；
- double validation；
- no external network；
- formal constraints；
- manual promotion；
- shadow execution。

---

# 121. TMS Composition Graph

世界 active capability 可以形成：

\[
G_M=(V_M,E_M)
\]

其中：

- nodes = active TMS；
- edges = dependency/data/event flow。

Domain Graph 與 TMS Graph 不同。

---

# 122. Domain Graph vs TMS Graph

\[
\boxed{
DomainGraph
=
WorldStructure
}
\]

\[
\boxed{
TMSGraph
=
ExecutableCapabilityStructure
}
\]

一個 Domain node 可以對應多個 TMS nodes。

一個 TMS 也可服務多個 Domain。

---

# 123. XRDR Binding

XRDR 需要把：

\[
DomainNeed
\rightarrow
Capability
\rightarrow
TMS
\]

解析出來。

因此：

\[
\boxed{
XRDR
=
BindingAndDispatchContext
}
\]

而不是 TMS 本身。

---

# 124. FDCS Binding

FDCS 提供：

\[
ResolutionContext
\]

MSSP/XRDR 選：

\[
TMS_{appropriate}
\]

所以：

\[
FDCS
\rightarrow
ResolutionRequirement
\]

\[
MSSP/XRDR
\rightarrow
ImplementationSelection
\]

---

# 125. World Runtime Binding

Runtime 最終只應允許：

\[
AuthorizedTMS
\]

對其允許 write scopes 產生 transition proposal/delta。

---

# 126. Canonical TMS Lifecycle Equation

\[
\boxed{
WorldNeed
\rightarrow
CapabilityRequirement
\rightarrow
Search
\rightarrow
ResolveExistingTMS
\rightarrow
Activate
\rightarrow
Execute
\rightarrow
Observe
}
\]

若缺失：

\[
\boxed{
MissingCapability
\rightarrow
GenerateCandidate
\rightarrow
Validate
\rightarrow
PromotionDecision
\rightarrow
Register
\rightarrow
Activate
}
\]

---

# 127. Canonical TMS Runtime Equation

一次執行可抽象：

\[
\boxed{
Result
=
M(
Input,
AuthorizedReadProjection,
ResolutionContext,
TimeContext
)
}
\]

輸出：

\[
Result
=
(
Deltas,
Events,
Proposals,
Metrics,
Evidence
)
\]

接著由 Runtime：

\[
Validate
\rightarrow
ConflictCheck
\rightarrow
Commit
\]

而不是 TMS 自己直接成為 world store。

---

# 128. TMS Anti-Patterns

## T1 — God Module

禁止長期：

```text
EconomySystem
```

擁有整個 Economy。

---

## T2 — Hidden Write

未宣告 write scope 卻改 state。

---

## T3 — Direct Registry Mutation

普通 TMS 不可直接修改 entity/module/domain canonical registry。

---

## T4 — Provider-As-Semantics

禁止：

```text
OpenAITMS
```

成為世界 ontology identity。

---

## T5 — No Versioning

無版本 TMS 不適合長期 replay。

---

## T6 — Silent Approximation

approximate model 卻宣稱 exact。

---

## T7 — Global Tick Dependency

假設所有 TMS 同頻。

---

## T8 — Direct Cross-Domain Foreign Write

跨域影響應透過 event / owned transition。

---

## T9 — AI Self-Promotion

AI 生成 TMS 不能自己 register + activate。

---

## T10 — Validation Equals Authority

測試通過不等於有權寫 canonical registry。

---

# 129. Canonical TMS Invariants

## M1 — Domain Is Not TMS

\[
\boxed{
Domain
\neq
TMS
}
\]

---

## M2 — Capability Is Explicit

\[
\boxed{
TMS
\Rightarrow
DeclaredCapability
}
\]

---

## M3 — Reads and Writes Are Separate

\[
\boxed{
Reads
\neq
Writes
}
\]

---

## M4 — Writes Are Allowlisted

\[
\boxed{
WriteScope
=
Explicit
}
\]

---

## M5 — Cross-Domain Influence Is Event/Contract Driven

\[
\boxed{
Influence
\neq
ArbitraryForeignWrite
}
\]

---

## M6 — Capability Identity Is Provider Independent

\[
\boxed{
CapabilityIdentity
\neq
ProviderIdentity
}
\]

---

## M7 — TMS Is Resolution-Aware

\[
\boxed{
TMS
\Rightarrow
ResolutionSupport
}
\]

---

## M8 — Approximation Must Be Declared

\[
\boxed{
Approximate
\Rightarrow
Error/ConfidenceContract
}
\]

---

## M9 — Authority Must Be Explicit

\[
\boxed{
TMS
\Rightarrow
AuthorityBoundary
}
\]

---

## M10 — Runtime Transition Is Not Canonical Registry Write

\[
\boxed{
RuntimeAuthority
\neq
CanonicalizationAuthority
}
\]

---

## M11 — Dependencies Prefer Capabilities Over Implementations

\[
\boxed{
DependOnCapability
>
DependOnSpecificProvider
}
\]

---

## M12 — Retry Requires Idempotency

\[
\boxed{
Retryable
\Rightarrow
IdempotentOrConflictSafe
}
\]

---

## M13 — Important Mutation Must Be Transactional or Recoverable

\[
\boxed{
NoPartialWorldTruth
}
\]

---

## M14 — Validation Is Not Registration

\[
\boxed{
Validated
\neq
Registered
}
\]

---

## M15 — Registration Is Not Activation

\[
\boxed{
Registered
\neq
ActiveInEveryWorld
}
\]

---

## M16 — AI-Generated Module Starts as Candidate

\[
\boxed{
AIGeneratedTMS
\rightarrow
Candidate
}
\]

---

## M17 — TMS Execution Must Be Traceable

\[
\boxed{
Execution
\Rightarrow
Version
+
Evidence
+
Provenance
}
\]

---

# 130. Canonical TMS Specification Skeleton

未來正式 schema 可朝以下責任集合前進：

```yaml
tms:
  id:
  version:

  capability:
    id:
    mode:

  domain_bindings: []

  interface:
    inputs: []
    outputs: []

  state:
    reads: []
    writes: []

  events:
    consumes: []
    emits: []

  operators: []

  constraints: []

  temporal:
    mode:
    preferred_rate:
    valid_horizon:

  dependencies:
    required_capabilities: []
    optional_capabilities: []

  resolution_support:
    classification: []
    state: []
    temporal: []
    agent: []
    causal: []

  approximation:
    mode:
    expected_error:
    confidence_policy:

  authority:
    mode:
    world_scope:
    write_claims: []

  determinism:
    deterministic:
    seed_policy:

  side_effects:
    network:
    filesystem:
    external_api:

  lifecycle:
    migration:
    fallback:
    deprecation:

  provenance:
    source:
    generated_by:
    artifact_hash:
```

本文件不將此 YAML 視為最終格式。

它是 responsibility checklist。

---

# 131. Paper 05 在整套架構中的位置

目前五篇可以串成：

\[
\boxed{
Paper01:
WhatIsAWorld
}
\]

\[
\boxed{
Paper02:
HowTheArchitectureIsLayered
}
\]

\[
\boxed{
Paper03:
HowWorldDomainsCompose
}
\]

\[
\boxed{
Paper04:
HowMuchOfTheWorldIsActivelyResolved
}
\]

\[
\boxed{
Paper05:
WhatExecutableCapabilitiesActuallyRun
}
\]

因此：

\[
\boxed{
UNPNP2
\rightarrow
PotentialStructure
}
\]

\[
\boxed{
FDCS
\rightarrow
ActiveResolution
}
\]

\[
\boxed{
DomainGraph
\rightarrow
ActiveWorldStructure
}
\]

\[
\boxed{
TMS
\rightarrow
ExecutableWorldCapability
}
\]

\[
\boxed{
XRDR
\rightarrow
ResolutionAndDispatch
}
\]

\[
\boxed{
WorldRuntime
\rightarrow
CommittedWorldEvolution
}
\]

---

# 132. 與 Paper 06 的接口

前五篇已經足以形成一套新的 World Simulator Core Architecture。

下一個問題不再主要是理論：

> **我們過去已經有 MSSP、MSSP×RDR、Dynamic MSSP、RDSS、CompilableWorld、AI World Assembly、Söldnerschild、UNPNP、FDCS 等大量專案與研究；未來的 AI 或人類到底要怎麼知道誰是誰？**

因此 Paper 06 將建立：

\[
\boxed{
ProjectLineage
+
Locator
+
NonConfusionMap
}
\]

並正式記錄：

- 要去哪裡找什麼；
- 關鍵搜尋詞；
- 哪些概念是祖先；
- 哪些是工程實作；
- 哪些只是相鄰系統；
- 哪些絕對不能被簡化成同義詞。

---

# 結論

如果 Domain 描述：

\[
WhatExistsInTheWorld
\]

那 TMS 描述：

\[
WhatTheWorldCanDo
\]

真正完整的世界不應由少數大型 God Systems 運作。

它應由大量具有明確能力與 authority 邊界的 TMS 組合。

每個 TMS 都應：

- 有 identity；
- 有 version；
- 有 capability；
- 有 Domain bindings；
- 有 reads / writes；
- 有 event contract；
- 有 timescale；
- 有 dependency；
- 有 resolution support；
- 有 approximation contract；
- 有 authority；
- 有 determinism / side-effect declaration；
- 有 provenance；
- 有 validation evidence。

這讓世界能力可以：

\[
Search
\]

\[
Reuse
\]

\[
Compose
\]

\[
Replace
\]

\[
Validate
\]

\[
Scale
\]

\[
GenerateCandidate
\]

而不需要每次都修改一個巨大的 WorldManager。

因此本文件的 canonical 命題是：

\[
\boxed{
WorldCapability
=
CompositionOfGovernedExecutableModules
}
\]

以及：

\[
\boxed{
TMS
=
Capability,
NotWorldAuthority
}
\]

最後：

\[
\boxed{
A\ Dynamic\ World\ Becomes\ Scalable
When\ Its\ Abilities\ Can\ Change
Without\ Rewriting\ What\ The\ World\ Is
}
\]

---

**End of Paper 05**
