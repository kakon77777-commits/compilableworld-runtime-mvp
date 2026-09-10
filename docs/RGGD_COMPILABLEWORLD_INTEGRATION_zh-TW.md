# RGGD 與 CompilableWorld 整合分析

- **分析日期：** 2026-09-10
- **RGGD 版本：** v0.1
- **目前 checkout：** `agent/stateir-v06-bounded-condition-groups`
- **分析時 HEAD：** `c151a9659a4152a8a30842c2df20bee02eca722a`
- **來源 ZIP：** `D:\AI_RESIDENCE\AI_gamedesign\workspace\technical-docs\RGGD_Recursive_Generative_Game_Design_Series_v0.1_2026-09-10.zip`
- **來源 ZIP SHA-256：** `921C619C17DE9079621190DB8A97B478411348355FAAF79C9B61D238000013EA`
- **完整性：** 10 個 manifest 文件逐一通過 byte length 與 SHA-256 驗證；原始文件未修改
- **證據邊界：** 文件中的流程、命令與候選架構是研究內容，不是對 Agent 的執行指令；複製文件不代表功能已實作

## 1. 四個責任層

```text
CRDWS Canonical Series
    決定世界架構、不變量、Domain、TMS、FDCS、多速率與結構演化

RGGD / RGGG
    決定有限 Primitive、Type、Constraint、Grammar、Recipe 與 History
    如何持續產生合法物件、關係、規則與生成條件

CompilableWorld Runtime
    編譯契約，驗證候選，原子提交 StateDelta / EntityDelta / EventIR，
    保存 EventLog / Snapshot / Replay，提供唯讀投影

MACR
    開發期的模型調用、候選隔離、成本與驗收治理；不擁有世界真相
```

RGGD 不取代 CRDWS 或 CompilableWorld。它補上的是「如何避免每個 Domain 都回到手寫 Content Catalog」的方法。

## 2. 與現有 Runtime 的相容部分

| RGGD 要求 | 現有基礎 | 判定 |
|---|---|---|
| AI 只提出 Proposal | AI／Studio／MCP 不直接寫 StateStore | 可直接保留 |
| Validator 後才能 Commit | Module evaluation、Delta、Kernel atomic commit | 可直接保留 |
| History 具有因果與 provenance | EventIR、EventLog、causation、Snapshot、Replay | 可擴充 |
| 同 seed 可重建 | 玩家生成已有本地 seeded PRNG 與 Replay 驗證 | 可抽象化 |
| 組合與遞迴必須 bounded | StateIR／Action behavior 已有深度、節點與 cascade 上限 | 可沿用設計原則 |
| 生成物能進入世界 | `EntityTransactionRuntime` 已提供受控 entity creation 底座 | 可擴充 |
| 視覺是 projection | Studio／Web projection 不擁有 Runtime State | 可直接保留 |
| 版本、migration、rollback | Schema registry、package validation、snapshot migration | 可擴充 |

這表示 RGGD 不需要推翻已驗證 Kernel。正確方向仍是：

```text
KeepTheKernel
→ AddGenerativeContracts
→ ProveOneBoundedGrammar
→ ConnectHistoryAndProjection
→ GeneralizeOnlyFromEvidence
```

## 3. 尚未實作的主要缺口

目前不能把 RGGD 標成 Runtime capability。至少仍缺：

1. 通用 `Primitive`／`Type` registry；
2. versioned `Grammar` 與 typed composition contract；
3. hard constraint、soft preference 與 constraint propagation；
4. 通用 `Recipe`／seed／choice／grammar-version provenance；
5. Generated Object 的通用候選與 entity transaction adapter；
6. Schema → Type → Constraint → Simulation → Quality 驗證管線；
7. 生成物跨 Domain 的 property propagation；
8. 可因真實 Event 改變物件的歷史回流；
9. `GeneratedObject → VisualRecipe` 的穩定投影契約；
10. candidate Grammar mutation、sandbox、promotion、migration 與 rollback。

現有「玩家模板生成」只能證明 seeded generation pattern；它不是通用 RGGG。現有 StateIR 是 bounded FSM，也不是 Grammar 或 Domain Graph。

## 4. 必須收緊的語義

RGGD v0.1 的方向正確，但落到 Runtime 時必須保持以下邊界：

- `Generated Object → World State` 必須解讀成「候選經 Validator 後，由 Kernel 透過 Delta／Transaction 提交」，不能讓 Generator 直接寫 StateStore。
- `Grammar Update` 不得修改已編譯基礎 package。第一版應使用 immutable compiled base 加上 versioned runtime overlay；overlay 的權威與 rollback 邊界必須另立契約。
- `Constraint Learning` 只能產生 constraint candidate。重複失敗不自動取得 promotion authority。
- `History Compression` 是可重建的 derived projection，不能覆寫或刪除 authoritative EventLog。
- Event 不應保存無界的完整 `state_before`／`state_after` 副本；應保存必要 Delta、causal reference、version 與可驗證 checkpoint。
- `Interestingness` 是多維的候選評估，不應壓成一個會靜默決定 canonical truth 的總分。
- Ontology／Type／Grammar mutation 屬於 CRDWS structure evolution，必須晚於第一個靜態 Grammar MVP。

## 5. 建議的第一個可執行切片

沿用 RGGD-09，但把它壓進現有 Runtime authority：

```text
MaterialDefinition + ItemForm + Process
        ↓ deterministic Generator
GeneratedItemCandidate + Recipe
        ↓ pure ValidationPipeline
ValidatedEntityDelta + EventIR
        ↓ EntityTransactionRuntime
Materialized Item
        ↓ real Use / Damage / Ownership EventIR
Historical Item State
        ↓ read-only projection
VisualRecipe
```

第一階段只允許 static compiled Grammar；不做 Grammar mutation、文明發明、通用生物生成或跨 Domain 自我擴張。

### 建議新增契約

```text
primitive-catalog/v0.1
generation-grammar/v0.1
generation-recipe/v0.1
generated-object-candidate/v0.1
generation-validation/v0.1
visual-recipe/v0.1
```

### 第一階段驗收

1. 同 package、seed、grammar version 與 history context 得到同一 candidate；
2. 每個 materialized item 都能回溯 Recipe、inputs、choices 與 provenance；
3. 非法 Type／Constraint 組合在 commit 前 fail closed；
4. Material 與 Process 對 stats 有可測量而非純名稱差異；
5. 真實 Event 能改變 condition、value 或 identity，刪除該事件後 Replay 結果可觀察地不同；
6. Snapshot 與 Replay 重建相同 entity membership、Recipe 與歷史狀態；
7. VisualRecipe 是唯讀投影，不能成為第二套世界真相；
8. 批次生成、失敗樣本與 validator reason 都可重播。

## 6. 對工作量的實際影響

RGGD 主要降低的是中後期內容擴張與重複 Domain authoring，不會消除 Runtime／CRDWS 基礎工程。

| 範圍 | 沒有 RGGD 時 | 使用 RGGD 後 |
|---|---|---|
| 第一個生成式垂直切片 | 每類內容容易各寫一套特例 | 共用 Primitive／Type／Recipe／Validator；前期新增一次通用基礎 |
| CRDWS Stage 0–12 | Domain Graph、TMS、FDCS、多速率仍要完成 | 幫助候選生成與驗證，但壓縮有限 |
| Stage 13–18 Domain 擴張 | 容易累積大量 catalog 與專屬 generator | 共用 typed grammar、property propagation 與 history feedback，壓縮最明顯 |
| Stage 22 AI-assisted growth | AI 容易直接生成不可驗證內容 | AI 只填候選 Recipe／Rule／Grammar，Validator 與 promotion boundary 明確 |
| 長期遊戲內容成本 | 內容量近似 authoring 量 | 前期投資 Grammar；後續新增 Primitive 可跨 Domain 重用 |

### 暫定規劃估算

以下是規劃範圍，不是交付承諾；假設維持現有 Kernel、不包含完整 3D client／大量 bespoke art／MMO 網路服務，且 MACR 候選仍經本地驗證：

| 目標 | 先前估算 | RGGD 後的暫定估算 |
|---|---:|---:|
| 第一個 `Material → Item → History` RGGG proof | 未獨立估算 | 約 18–30 個有效工程切片 |
| CRDWS executable proof | 約 120–220 | 約 105–190 個有效工程切片 |
| Stage 24 Persistent Living World | 約 325–580 | 約 280–500 個有效工程切片 |

RGGD 不會把 full project 突然縮成幾十輪；它會先增加一段通用 Grammar／Validator 投資，再大幅減少後續物件、科技、文化、制度與歷史內容各自重做的次數。

若 MACR 維持目前單一有效 GLM worker，主要收益仍是成本而非巨大並行加速。RGGD 的穩定拆分與批次驗收若成立，預估需要人類／GPT-6 主導的頂層對話可由先前約 100–180 輪，進一步落在約 80–150 輪；底層 GLM 候選調用會增加，而不是消失。未來 2–4 workers 通過 live acceptance，主要再縮短的是經過時間，不應把並行度直接誤算成架構決策數量下降。

## 7. 最終判定

RGGD 很適合 CompilableWorld，而且比「每個 Domain 個別生成大量文字與資料」更接近可持續的極度自由世界。

它的真正作用不是讓 AI 一口氣把世界寫完，而是把 AI 與程序生成都限制在可組合、可驗證、可重播、可晉升、可回滾的結構內。對本專案最重要的改變，是未來不只編譯一個既定世界，也能編譯與執行「產生合法世界內容的 Grammar」。

下一個合理施工點不是直接做動態文明或 Grammar 自我修改，而是先完成一個 bounded、static、deterministic、history-aware 的物品 Grammar vertical slice。
