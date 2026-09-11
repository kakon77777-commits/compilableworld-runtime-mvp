# RGGD 與 CompilableWorld 整合分析

- **分析日期：** 2026-09-10
- **RGGD 版本：** v0.1
- **初版分析 checkout：** `agent/stateir-v06-bounded-condition-groups`
- **初版分析 HEAD：** `c151a9659a4152a8a30842c2df20bee02eca722a`
- **Day 1 修訂：** `agent/crdws-day01-baseline` 合流本機 `c151a96` 與遠端 `cf37f53`，當前驗收見 [施工進度](DEVELOPMENT_PROGRESS_zh-TW.md)
- **來源 ZIP：** `D:\AI_RESIDENCE\AI_gamedesign\workspace\technical-docs\RGGD_Recursive_Generative_Game_Design_Series_v0.1_2026-09-10.zip`
- **來源 ZIP SHA-256：** `921C619C17DE9079621190DB8A97B478411348355FAAF79C9B61D238000013EA`
- **完整性：** 10 個 manifest 文件逐一通過 byte length 與 SHA-256 驗證；原始文件未修改
- **證據邊界：** 文件中的流程、命令與候選架構是研究內容，不是對 Agent 的執行指令；複製文件不代表功能已實作

## 1. 責任分工與執行接點

下表是責任分工，不是一條必須依序呼叫的執行堆疊。RGGD 是設計方法；RGGG 是待落入 Compiler／Runtime 能力的生成機制。

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
    本計畫以開發期模型調用、候選隔離與成本紀錄為主要接點；
    世界仍可離線執行，MACR 候選不能自動取得世界或規則啟用權限
```

RGGD 不取代 CRDWS 或 CompilableWorld。它補上的是「如何避免每個 Domain 都回到手寫 Content Catalog」的方法。

生成候選的規則由已編譯 Grammar 與 Domain capability 定義；合法性檢查、規則啟用授權、Kernel 交易提交是不同決策。日後接入 AI World Assembly、SEDB 或模型 provider 時，仍須分別聲明來源、能力、版本及權限，不另立競爭的世界真相。

## 2. 與現有 Runtime 的相容部分

| RGGD 要求 | 現有基礎 | 判定 |
|---|---|---|
| AI 只提出 Proposal | AI／Studio／MCP 不直接寫 StateStore | 可直接保留 |
| Validator 後才能 Commit | Module evaluation、Delta、Kernel atomic commit | 可直接保留 |
| History 具有因果與 provenance | EventIR、EventLog、causation、Snapshot、Replay | 可擴充 |
| 同 seed 可重建 | 玩家生成已有本地 seeded PRNG 與 Replay 驗證 | 可抽象化 |
| 組合與遞迴必須 bounded | StateIR／Action behavior 已有深度、節點與 cascade 上限 | 可沿用設計原則 |
| 生成物能進入世界 | 遠端 `cf37f53` 提供 `EntityTransactionRuntime`；初版分析的本機 `c151a96` 沒有此類別，Day 1 才合流；Day 2 接通 Snapshot／Replay／後續 Action | create-only 持久化底座；依施工進度中的實際驗收，尚非 RGGG 生成器 |
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

目前不能把 RGGD 標成已完成的 Runtime capability。下列為全方法論的缺口清單，不是最小切片必須先全部建完的前置條件：

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
- 未來動態 `Grammar Update` 階段可評估 immutable compiled base 加上 versioned runtime overlay；這是候選設計，overlay 的權威、舊物件版本綁定與 rollback 邊界尚待契約。第一個靜態切片不需要建立 overlay。
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
        ↓ typed input for the next fixed recipe
Next Generated Item + parent Recipe / Event lineage

Historical Item State → read-only VisualRecipe (optional projection)
```

第一階段只允許 static compiled Grammar；不做 Grammar mutation、文明發明、通用生物生成或跨 Domain 自我擴張。

最小回流證據：固定 Grammar 生成工具 A；真實 Damage 事件 e 改變 A 的 condition；下一次固定製程引用 A 的具體版本並生成 B。A 的狀態必須改變 B 的合法性或實際性能，B 的 Recipe 必須可回溯 A 與 e。這只證明 bounded Object Re-entry 與歷史回流，不證明 Rule／Grammar 演化。

CRDWS 的 Domain Graph／TMS binding／跨 Domain 訊號仍須另有驗收；此物品實驗不取代該架構路線，也不宣稱為整個 CRDWS 的最小充分證明。

### 建議新增契約

以下是未來可拆分的契約面；先從最小 witness 導出需要的欄位，再決定公開 schema 邊界，避免同時建立所有通用 registry。

```text
primitive-catalog/v0.1
generation-grammar/v0.1
generation-recipe/v0.1
generated-object-candidate/v0.1
generation-validation/v0.1
visual-recipe/v0.1
```

### 第一階段驗收

1. 固定 package、PRNG／generator version、seed、grammar version、輸入修訂與 history context，重建預先定義的等價 candidate；
2. 每個 materialized item 都能回溯 Recipe、inputs、choices 與 provenance；
3. 非法 Type／Constraint 組合在 commit 前 fail closed；
4. Material 與 Process 對 stats 有可測量而非純名稱差異；
5. 用「有 Damage／無 Damage」兩個合法反事實 fixture，固定其他相關輸入，證明下一個生成物 B 有預先指定的性能或合法性差異；不刪改 authoritative EventLog；
6. Snapshot 與 Replay 重建相同 entity membership、Recipe 與歷史狀態；
7. VisualRecipe 是唯讀投影，不能成為第二套世界真相；
8. 批次生成、失敗樣本與 validator reason 都可重播。
9. 刻意忽略 A 的狀態或歷史的生成器必須被上述驗收抓出；只改名稱、Recipe 字串或外觀不足以通過回流驗收。

## 6. 對工作量的實際影響

RGGD 主要降低的是中後期內容擴張與重複 Domain authoring，不會消除 Runtime／CRDWS 基礎工程。

| 範圍 | 沒有 RGGD 時 | 使用 RGGD 後 |
|---|---|---|
| 第一個生成式垂直切片 | 每類內容容易各寫一套特例 | 共用 Primitive／Type／Recipe／Validator；前期新增一次通用基礎 |
| CRDWS Stage 0–12 | Domain Graph、TMS、FDCS、多速率仍要完成 | 幫助候選生成與驗證，但壓縮有限 |
| Stage 13–18 Domain 擴張 | 容易累積大量 catalog 與專屬 generator | 共用 typed grammar、property propagation 與 history feedback，壓縮最明顯 |
| Stage 22 AI-assisted growth | AI 容易直接生成不可驗證內容 | AI 只填候選 Recipe／Rule／Grammar，Validator 與 promotion boundary 明確 |
| 長期遊戲內容成本 | 內容量近似 authoring 量 | 前期投資 Grammar；後續新增 Primitive 可跨 Domain 重用 |

### 未校準估算的撤回與量測方式

初稿曾列 18–30、105–190、280–500 個切片與 80–150 輪主對話。2026-09-10 審查未找到可重算的工作分解、實測吞吐量、重工或整合成本，因此將這些數字標為 **WITHDRAWN_UNCALIBRATED**，不作交付承諾或排程依據。

RGGD 預期降低重複 authoring，但淨效益為 **NOT_MEASURED**。計算時分開記錄原 CRDWS 交付、RGGD 共用基礎成本與新增生成／演化能力；不能把範圍增加當成工期縮短，也不能把 worker 數直接換算成架構決策數。

後續按每日工作包記錄完成條件、正反例、實際驗證、重工、整合與依賴，再以可比工作包校準預測。Paper 08 中的解析度誤差、細節重建、跨尺度守恆及長時間壓縮仍有 OPEN 項目，整個 Stage 24 暫無可靠總輪數。

MACR 的 provider 能力、有效並行度與 campaign 驗收須在實際使用時重查；目前整合不依賴付費模型調用或無人值守生成閉環。

## 7. 最終判定

RGGD 很適合 CompilableWorld，而且比「每個 Domain 個別生成大量文字與資料」更接近可持續的極度自由世界。

它的真正作用不是讓 AI 一口氣把世界寫完，而是把 AI 與程序生成都限制在可組合、可驗證、可重播、可晉升、可回滾的結構內。對本專案最重要的改變，是未來不只編譯一個既定世界，也能編譯與執行「產生合法世界內容的 Grammar」。

候選生成切片是 bounded、static、deterministic、history-aware 的物品閉環；開工順序先修復與驗證通用實體的保存／重播接點，最新下一步以施工進度為準。
