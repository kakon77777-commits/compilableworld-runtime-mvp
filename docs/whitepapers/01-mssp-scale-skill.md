---
title: "MSSP-Scale Skill：母集與子集範式在大型 AI Agent 技能系統中的通用化"
subtitle: "從單一提示文件到可理解、可調度、可治理、可演化的技能母集架構"
author: "Neo.K / EVEMISSLAB"
version: "v0.1"
status: "方法論論文草案"
date: "2026-07-12"
language: "zh-TW"
keywords:
  - MSSP
  - Mother-Set and Subset Paradigm
  - AI Agent
  - Skill System
  - FMS
  - SMS
  - TMS
  - SCL
  - DMS
  - Context Engineering
  - Agent Governance
---

# MSSP-Scale Skill：母集與子集範式在大型 AI Agent 技能系統中的通用化

## 摘要

本文提出「MSSP-Scale Skill」，即將母集與子集範式（Mother-Set and Subset Paradigm, MSSP）從一般軟體架構方法論，推進為大型 AI Agent 技能系統的通用組織方法。

傳統 Agent Skill 往往被實作為單一 `SKILL.md`、大型系統提示、工具說明集合、固定工作流程或若干散落的參考文件。這種方式在功能少、任務單純、上下文規模有限時尚可運作；但當技能開始涵蓋多種角色、多個工具、不同風險等級、數十種子任務、可插拔領域能力、版本遷移與長期維護時，單一 Skill 會迅速形成提示單體、上下文膨脹、能力耦合、權限混淆與自我描述失效等問題。

MSSP-Scale Skill 的核心主張是：

> 大型 Skill 不應被理解為一份更長的提示文件，而應被理解為一個具有系統本體、核心能力、可插拔能力、設定契約、觀測層與任務路由的技能母集系統。

在此架構中：

- FMS 定義技能系統是什麼、為何存在、服務哪些任務，以及各模組如何被定位；
- SCL 定義系統允許由誰、在何種條件下、以何種權限與風險等級被改變；
- SMS 保存任何任務閉環都不可缺少的穩定核心能力；
- TMS 保存按需載入、可替換、可獨立測試的專門能力；
- DMS 保存日誌、追蹤、測試、報告與人類可理解的執行狀態；
- Router 根據任務意圖、風險、工具、資料來源與上下文預算，動態選擇真正需要載入的技能子集。

本文將此方法形式化為一種「上下文感知能力架構」，並提出依賴規則、孤島測試、能力契約、風險分級、版本治理與規模演化路徑。本文亦區分 Skill、Prompt、Workflow、Plugin、Tool 與 Agent 的不同角色，說明 MSSP-Scale Skill 並非另一種資料夾命名規則，而是一套讓人類與 Agent 都能理解、導航、載入、驗證與維護複雜能力系統的認知外骨骼。

本文僅建立通用理論與結構，不針對特定 MUD、遊戲、研究或軟體專案實作。後續可依此方法建立各領域專用的 MSSP 規模 Skill System。

**關鍵詞：** MSSP、AI Agent、Skill、上下文工程、能力架構、FMS、SMS、TMS、SCL、DMS、模組化、Agent 治理

---

# 第一章　問題提出：Skill 正在重演軟體單體化

## 1.1 從短提示到技能單體

早期的 AI Agent Skill 通常只需要回答有限問題，例如：

- 如何使用某個工具；
- 如何處理某種格式；
- 如何執行一段固定流程；
- 如何遵守某一組領域規範；
- 如何產生某一類輸出。

在此規模下，一份數百行以內的說明文件足以提供：

```text
何時啟用
需要哪些輸入
應執行哪些步驟
可使用哪些工具
輸出必須符合什麼格式
```

然而，一旦技能持續擴張，單一文件便會逐漸同時承擔：

- 系統總敘事；
- 任務辨識；
- 工具說明；
- 權限規則；
- 領域知識；
- 錯誤處理；
- 測試方法；
- 輸出模板；
- 版本紀錄；
- 安全政策；
- 子工作流程；
- 特定平台適配；
- 特定資料來源適配。

此時，Skill 便不再是一項技能，而是一個未被承認的軟體系統。

問題在於，它仍然被當成一份文件維護。

---

## 1.2 提示單體的五種結構性失效

### 1.2.1 上下文全量載入

單一 Skill 常以整份文件注入 Agent 上下文。即使任務只需要其中一項能力，Agent 仍被迫讀取全部規則。

設完整技能知識為：

$$
K =
\bigcup_{i=1}^{n} K_i
$$

傳統做法為：

$$
K_{\mathrm{loaded}} = K
$$

但某一任務 $q$ 實際只需要：

$$
K_q \subset K
$$

因此產生上下文浪費：

$$
W_q =
\left|K\right| -
\left|K_q\right|
$$

當技能規模增加，$W_q$ 通常同步增加。

### 1.2.2 能力互相污染

若所有子任務規則都存在同一文件中，Agent 可能把某個領域的要求錯誤套用到另一個領域。

例如：

- 程式碼審查規則污染純文字寫作；
- 高風險部署規則污染只讀分析；
- 特定平台格式污染通用輸出；
- 某資料來源的權限假設被帶到另一資料來源；
- 測試 Agent 的後台視角污染模擬使用者的有限視角。

這不是模型單純「沒讀懂」，而是技能邊界未被結構化。

### 1.2.3 隱藏依賴

一個子流程表面上可獨立執行，實際卻依賴同一文件內其他段落所定義的：

- 名詞；
- 權限；
- 工具；
- 輸出格式；
- 前置資料；
- 例外條件。

當技能被拆分、搬移或版本更新後，這些隱藏依賴便會失效。

### 1.2.4 權限與知識混合

許多 Skill 同時描述「Agent 知道什麼」與「Agent 可以做什麼」。

但知識與權限不是同一件事。

Agent 可以知道如何刪除資料，不代表它應擁有刪除資料的工具權限；可以理解正式部署流程，不代表它可直接發布；可以閱讀安全策略，不代表它可以改寫安全策略。

若兩者混合，Agent 的能力邊界便只剩自然語言自律，而缺乏架構約束。

### 1.2.5 維護與版本失真

當單一 Skill 文件過長時，任何修改都可能影響不相關工作流。維護者通常無法快速回答：

- 修改了哪一項能力？
- 哪些任務會受影響？
- 是否改變權限？
- 是否破壞既有輸出？
- 是否需要遷移？
- 是否仍能與舊工具版本相容？

這與大型軟體中的「牽一髮動全身」完全相同。

---

# 第二章　MSSP 的原始精神及其 Skill 化條件

## 2.1 MSSP 不是一般分層架構

母集與子集範式的核心，不是單純把檔案分成三層，而是建立一套符合人類認知順序的系統結構。

其基本隱喻來自教科書：

```text
前言   → 系統目的與範圍
目錄   → 系統導航
章節   → 核心內容與專門內容
索引   → 概念到位置的映射
註釋   → 版本、決策與限制
```

這一隱喻的重要性在於：使用者不必先讀完全部內容，才知道整本書在做什麼。

同理，一個好的 Skill System 也不應要求 Agent 先載入全部能力，才能知道該使用哪個能力。

---

## 2.2 MSSP 的三個基本母集

### 2.2.1 FMS：第一主母集

FMS（First Mother Set）是系統的本體聲明與元資料中樞。

它回答：

- 這是什麼系統？
- 它為何存在？
- 服務哪些使用者與任務？
- 核心價值是什麼？
- 非目標是什麼？
- 有哪些核心能力？
- 有哪些可插拔能力？
- 模組在哪裡？
- 重大設計決策為何？

FMS 的基本原則是：

> 純元資料，零業務執行邏輯。

### 2.2.2 SMS：第二主母集

SMS（Second Mother Set）保存系統不可缺少的核心能力。

判斷標準不是「很常用」，而是：

> 移除此模組後，系統是否仍然是原本那個系統？

若移除後系統的基本任務閉環失效，該能力屬於 SMS。

### 2.2.3 TMS：第三主母集

TMS（Third Mother Set）保存可插拔、可替換、可獨立理解與測試的功能子集。

TMS 可以：

- 按需載入；
- 獨立版本化；
- 由不同團隊維護；
- 針對不同平台替換；
- 根據任務選擇；
- 在不改動核心的情況下新增。

MSSP 的重點不只是分層，而是讓 TMS 不必透過彼此直接耦合來完成任務。

---

## 2.3 Skill 化所需要的延伸層

當 MSSP 應用到 AI Agent Skill 時，三個母集仍然必要，但不足以描述權限、觀測與執行路由。

因此，通用 Skill 系統還需要：

- SCL：設定與可變性契約；
- DMS：診斷、觀測與人類可見狀態；
- Router：任務辨識與上下文調度；
- Runtime：真正執行工具與工作流的環境。

這些延伸不改變 MSSP 的核心，而是使其適合 Agent 時代。

---

# 第三章　MSSP-Scale Skill 的核心定義

## 3.1 定義

本文將 MSSP-Scale Skill 定義為：

> 一個以母集與子集範式組織，能根據任務選擇性載入知識、能力、工具契約與治理規則，並可被獨立測試、觀測、版本化與擴張的 Agent 技能系統。

其形式可表示為：

$$
\mathcal{K}
=
(
F,
C,
S,
T,
D,
R,
X
)
$$

其中：

- $F$：FMS，本體與導航；
- $C$：SCL，設定、權限與可變性契約；
- $S$：SMS，核心能力集合；
- $T$：TMS，可插拔能力集合；
- $D$：DMS，觀測與診斷集合；
- $R$：Router，任務路由函數；
- $X$：Runtime，工具與實際執行環境。

---

## 3.2 Skill、Prompt、Workflow、Tool、Plugin 與 Agent 的區別

Prompt 是一次或一段上下文中的指令；Skill 是可重複使用的能力契約。

$$
\mathrm{Prompt}
=
\text{Instruction Instance}
$$

$$
\mathrm{Skill}
=
\text{Reusable Capability Contract}
$$

Workflow 描述步驟順序；Skill 描述完成某類任務所需要的能力與規則。

Tool 提供可執行操作；Skill 決定何時使用、為何使用、使用前需要什麼、使用後如何驗證，以及何時禁止使用。

Plugin 是部署、封裝或整合形式。一個 Plugin 可以包含多個 Skill；一個 Skill 也可以跨越多個 Plugin 或工具來源。

Agent 是執行與決策主體；Skill 是 Agent 可載入的能力結構。

因此：

$$
\mathrm{Agent}
+
\mathrm{Skill}
+
\mathrm{Tool}
+
\mathrm{Context}
\rightarrow
\mathrm{Action}
$$

---

# 第四章　FMS：技能系統的本體與導航母集

## 4.1 FMS 在 Skill 中的功能

FMS 不教 Agent 如何完成每個細節，而是提供一張可以迅速理解全域的認知地圖。

它至少應包含：

```text
系統敘事
任務範圍
非目標
核心概念
能力索引
依賴圖
風險分級
版本政策
設計決策
維護責任
```

## 4.2 Skill FMS 的最低文件集合

```text
FMS/
├── 00_SYSTEM_NARRATIVE.md
├── 01_SCOPE_AND_NON_GOALS.md
├── 02_ARCHITECTURE_MAP.md
├── 03_CAPABILITY_INDEX.yaml
├── 04_TERMINOLOGY.md
├── 05_DECISION_LOG.md
├── 06_VERSION_POLICY.md
└── 07_RISK_CLASSIFICATION.md
```

## 4.3 FMS 必須保持不可執行性

FMS 若混入大量具體流程，會逐漸變成另一份大型 Skill。

因此 FMS 應限制為：

- 描述；
- 索引；
- 契約引用；
- 高階架構；
- 版本與治理資訊。

它不應包含：

- 完整程式碼；
- 特定平台大量細節；
- 長篇領域資料；
- 每個子技能的全部步驟；
- 直接工具呼叫參數。

## 4.4 FMS 是人類與 Agent 的共同導航層

傳統 README 主要服務人類。

MSSP-Scale Skill 的 FMS 同時服務：

- 使用者；
- 開發者；
- 維護者；
- Router；
- 執行 Agent；
- 審查 Agent；
- 測試 Agent。

因此 FMS 應盡量同時具有人類可讀與機器可讀形式。

---

# 第五章　SCL：技能系統的可控制性與權限契約

## 5.1 為什麼 Skill 必須有 SCL

FMS 定義系統是什麼，但不能充分回答：

- 哪些行為可被改變？
- 誰可以改？
- Agent 可以使用哪些工具？
- 哪些操作需要人工批准？
- 哪些設定可熱更新？
- 哪些資訊可被哪種角色讀取？
- 哪些風險等級允許自動化？

因此，Skill System 需要設定契約層。

SCL 可定義為：

> 將技能能力、工具權限、設定範圍、風險等級與批准流程轉換為機器可驗證契約的控制層。

## 5.2 知識權與操作權分離

設某 Agent 角色為 $a$，某能力為 $k$，某操作為 $o$。

理解某能力：

$$
\mathrm{Know}(a,k)=1
$$

不代表允許操作：

$$
\mathrm{Permit}(a,o)=1
$$

兩者必須分開。

## 5.3 SCL 最低組成

```text
SCL/
├── settings.schema.json
├── permissions.policy.yaml
├── risk-levels.yaml
├── tool-access.yaml
├── approval-policy.yaml
├── data-boundaries.yaml
├── runtime-limits.yaml
└── migration-policy.yaml
```

## 5.4 修改風險分級

### L0：表達層修改

例如文案、格式、非關鍵說明與顯示方式。

### L1：內容層修改

例如新增一般資料、更新參考內容、增加模板或新增低風險子能力。

### L2：行為參數修改

例如閾值、排序權重、重試次數、成本配額與模型選擇。

### L3：工作流與邏輯修改

例如新增工具、改變決策流程、改寫驗證邏輯與修改輸出契約。

### L4：核心治理與安全修改

例如權限、認證、正式部署、資料刪除、祕密管理與核心 Skill 路由。

不同等級應對應不同測試與批准要求。

---

# 第六章　SMS：不可缺少的核心技能母集

## 6.1 SMS 的判斷標準

Skill System 中，某模組屬於 SMS，應至少符合下列一項：

1. 所有主要任務都需要；
2. 缺少它便無法形成完整閉環；
3. 其他模組必須依賴它所提供的穩定接口；
4. 它承擔安全、驗證、版本或核心資料契約；
5. 移除後，系統不再具有原本的身份。

## 6.2 通用 SMS 類型

不同領域會有不同 SMS，但大型 Skill 常見以下核心：

```text
意圖解析
輸入正規化
核心資料模型
能力契約
驗證
工具抽象
結果整合
錯誤處理
版本相容
安全治理
```

## 6.3 SMS 必須穩定，不等於不能改

穩定表示：

- 有清楚接口；
- 版本更新受控；
- 依賴者不需頻繁同步修改；
- 具備回歸測試；
- 變更有遷移政策。

並非表示永遠凍結。

## 6.4 SMS 不應直接包含所有領域能力

如果所有功能都被宣稱為核心，SMS 便會再次成為單體。

因此應定期詢問：

> 若移除此能力，系統是否仍可完成核心任務？

若可以，該能力更可能屬於 TMS。

---

# 第七章　TMS：可插拔、可替換、可按需載入的技能子集

## 7.1 TMS 的基本性質

一個健康的 TMS 應具備：

- 單一明確目的；
- 清楚輸入；
- 清楚輸出；
- 可列舉依賴；
- 可獨立測試；
- 可由 Router 判斷是否載入；
- 移除後不破壞核心系統；
- 不直接依賴其他 TMS 的內部實作。

## 7.2 TMS 的常見分類

### 平台適配類

```text
GitHub
Google Drive
特定遊戲引擎
特定雲端
特定資料庫
特定文件格式
```

### 領域能力類

```text
法律
金融
醫療
遊戲設計
學術研究
翻譯
程式開發
```

### 角色類

```text
規劃者
執行者
審查者
測試者
模擬使用者
維運者
```

### 輸出類

```text
報告
簡報
程式碼
資料庫
圖表
互動介面
部署包
```

## 7.3 禁止 TMS 網狀依賴

理想依賴為：

$$
T_i \rightarrow S_j
$$

而不是：

$$
T_i
\rightarrow
T_j
\rightarrow
T_k
\rightarrow
T_i
$$

若兩個 TMS 需要合作，應透過 SMS 所定義的共享接口或事件契約。

```text
TMS-A
   ↓
SMS-Shared-Contract
   ↑
TMS-B
```

## 7.4 孤島測試

測試方式：

1. 建立最小 Agent Runtime；
2. 只載入必要 SMS；
3. 載入單一 TMS；
4. Mock 外部工具；
5. 執行該 TMS 的代表任務；
6. 驗證輸入、輸出與權限；
7. 確認不依賴其他 TMS。

若無法獨立通過，表示存在隱性耦合。

---

# 第八章　DMS：觀測、診斷與人類可見狀態

## 8.1 Agent 成功不等於人類看得懂

Agent 可能知道：

- 呼叫了哪些工具；
- 哪個步驟成功；
- 哪個測試失敗；
- 哪個檔案被修改；
- 哪個權限被拒絕。

但使用者可能只看到一句「完成」。

這會形成不可見性債務。

因此大型 Skill 必須具備 DMS（Diagnostic Mother Set 或 Diagnostic/Monitoring Set）。

## 8.2 DMS 應記錄什麼

```text
任務路由
已載入技能
工具呼叫
輸入來源
輸出位置
驗證結果
錯誤
重試
風險判定
人工批准
版本資訊
成本與延遲
```

## 8.3 DMS 的兩種視圖

### 機器視圖

供 Agent、測試系統與維運使用。

### 人類視圖

供使用者理解：

```text
已讀取來源資料。
已使用指定平台適配能力。
已完成格式驗證。
未修改正式環境。
輸出已建立於指定位置。
```

---

# 第九章　Router：上下文與能力的動態調度

## 9.1 Router 是 Skill System 的執行入口

Router 的任務不是完成實際工作，而是回答：

- 這是什麼任務？
- 需要哪些核心能力？
- 需要哪些 TMS？
- 是否需要工具？
- 風險等級為何？
- 是否需要人工批准？
- 上下文預算是多少？
- 哪些模組不應載入？

## 9.2 路由函數

設任務為 $q$，使用者上下文為 $u$，可用工具為 $\tau$，權限狀態為 $p$。

Router 可表示為：

$$
R(q,u,\tau,p)
\rightarrow
(
S_q,
T_q,
C_q,
D_q
)
$$

其中：

- $S_q$：必要 SMS；
- $T_q$：選定 TMS；
- $C_q$：適用 SCL 契約；
- $D_q$：需要的觀測策略。

## 9.3 最小載入原則

任務上下文應滿足：

$$
K_{\mathrm{loaded}}
=
F_{\mathrm{minimal}}
\cup
C_q
\cup
S_q
\cup
T_q
$$

而非全量載入整個技能系統。

## 9.4 上下文效用密度

可定義上下文效用密度：

$$
\rho_q
=
\frac{
I_{\mathrm{task\ relevant}}
}{
I_{\mathrm{loaded}}
}
$$

理想狀況為：

$$
\rho_q \rightarrow 1
$$

全量 Skill 注入往往使 $\rho_q$ 隨規模下降。

---

# 第十章　能力契約

## 10.1 每個子技能都應有契約

一個技能模組不應只寫「你要怎麼做」，還要聲明：

```text
能力名稱
用途
啟用條件
輸入
輸出
必要依賴
可用工具
禁止操作
失敗模式
驗證方法
版本
風險
```

## 10.2 通用契約示例

```yaml
id: tms.example.capability
version: 0.1.0
purpose: 將來源資料轉換為目標格式

activate_when:
  task_type: transformation
  target_format: example

inputs:
  - source_document
  - transformation_options

outputs:
  - transformed_artifact
  - validation_report

requires:
  sms:
    - source_intake
    - validation
  tools:
    - file_reader
    - file_writer

permissions:
  may:
    - read_user_source
    - create_output_file
  may_not:
    - overwrite_source
    - publish_externally

risk_level: 1

tests:
  - schema_validation
  - round_trip_test
```

## 10.3 輸出不是完成證明

Agent 生成輸出不等於任務完成。

能力契約應定義完成條件：

$$
\mathrm{Done}
=
\mathrm{OutputCreated}
\land
\mathrm{Validated}
\land
\mathrm{Accessible}
\land
\mathrm{Reported}
$$

高風險任務可能還需要：

$$
\mathrm{Done}_{H}
=
\mathrm{Done}
\land
\mathrm{Approved}
\land
\mathrm{Audited}
$$

---

# 第十一章　MSSP-Scale Skill 的一般目錄結構

```text
skill-system/
├── SKILL.md
│
├── FMS/
│   ├── 00_SYSTEM_NARRATIVE.md
│   ├── 01_SCOPE_AND_NON_GOALS.md
│   ├── 02_ARCHITECTURE_MAP.md
│   ├── 03_CAPABILITY_INDEX.yaml
│   ├── 04_TERMINOLOGY.md
│   ├── 05_DECISION_LOG.md
│   ├── 06_VERSION_POLICY.md
│   └── 07_RISK_CLASSIFICATION.md
│
├── SCL/
│   ├── settings.schema.json
│   ├── permissions.policy.yaml
│   ├── tool-access.yaml
│   ├── approval-policy.yaml
│   ├── runtime-limits.yaml
│   └── migration-policy.yaml
│
├── SMS/
│   ├── intent-routing/
│   ├── input-normalization/
│   ├── core-model/
│   ├── validation/
│   ├── tool-abstraction/
│   ├── result-assembly/
│   └── error-handling/
│
├── TMS/
│   ├── domains/
│   ├── adapters/
│   ├── roles/
│   ├── formats/
│   └── workflows/
│
├── DMS/
│   ├── logging/
│   ├── tracing/
│   ├── metrics/
│   ├── reports/
│   └── human-visible-state/
│
├── schemas/
├── templates/
├── examples/
├── tests/
└── migrations/
```

---

# 第十二章　規模感知：何時需要 MSSP-Scale Skill

## 12.1 小型 Skill

特徵：

- 單一任務；
- 單一工具或無工具；
- 少量規則；
- 無高風險操作；
- 無插件需求；
- 無多角色。

可使用：

```text
SKILL.md
examples/
tests/
```

## 12.2 中型 Skill

特徵：

- 多個相關任務；
- 兩至五個工具；
- 少量平台差異；
- 有基本設定與測試；
- 開始需要模組化。

可使用：

```text
FMS
SMS
TMS
tests
```

## 12.3 大型 Skill System

當出現以下任意多項條件時，應考慮 MSSP-scale：

- 超過三種主要角色；
- 超過五個外部工具；
- 超過十個子能力；
- 同時存在只讀與寫入操作；
- 存在高風險動作；
- 不同任務需要不同上下文；
- 多平台適配；
- 需長期版本維護；
- 多人或多 Agent 協作；
- 需要獨立測試子能力；
- 需要按需載入；
- 單一 Skill 文件已難以在數分鐘內說清楚。

## 12.4 不應過早 MSSP 化

MSSP 不是要求所有 Skill 一開始就建立龐大目錄。

過早分層會造成：

- 空模組；
- 虛假抽象；
- 維護成本；
- 導航負擔；
- 尚未驗證的邊界被過早固定。

因此應遵循：

> 規模不足時保持簡單；邊界出現時再正式分集。

---

# 第十三章　版本、遷移與演化

## 13.1 Skill 版本不是文件版本而已

大型 Skill 的版本至少包含：

```text
System Version
FMS Version
Contract Version
SMS Version
TMS Version
Tool Compatibility Version
Output Schema Version
```

## 13.2 版本相容矩陣

```yaml
system_version: 1.2.0

compatible:
  sms.core-model: ">=1.0,<2.0"
  tms.adapter-x: ">=0.4"
  tool.api-x: "2026-05"
  output.schema: "2.x"
```

## 13.3 遷移

當能力契約改變時，需要定義：

- 舊輸入如何轉換；
- 舊輸出是否仍可讀；
- 舊 TMS 是否仍可掛載；
- 哪些工具版本失效；
- 哪些權限需要重新批准。

遷移函數可表示為：

$$
M_{v_a \to v_b}
:
K_{v_a}
\rightarrow
K_{v_b}
$$

---

# 第十四章　測試策略

## 14.1 測試分層

### 契約測試

驗證輸入、輸出、權限與依賴。

### 孤島測試

驗證單一 TMS 在最小核心下能否運作。

### 路由測試

驗證 Router 是否選擇正確能力，並避免多載入無關模組。

### 工具測試

驗證工具錯誤、拒絕、超時與格式變更。

### 回歸測試

驗證更新核心或契約後，既有代表任務仍可完成。

### 安全測試

驗證越權、提示注入、資料外洩與高風險操作防護。

### 人類可見狀態測試

驗證使用者是否能理解做了什麼、改了什麼、哪裡輸出、是否成功與哪些未完成。

## 14.2 測試覆蓋率

能力覆蓋率：

$$
C_K
=
\frac{
\left|K_{\mathrm{tested}}\right|
}{
\left|K_{\mathrm{declared}}\right|
}
$$

路由覆蓋率：

$$
C_R
=
\frac{
\left|Q_{\mathrm{correctly\ routed}}\right|
}{
\left|Q_{\mathrm{test}}\right|
}
$$

權限拒絕正確率：

$$
C_P
=
\frac{
\left|O_{\mathrm{correctly\ denied}}\right|
}{
\left|O_{\mathrm{forbidden\ test}}\right|
}
$$

---

# 第十五章　反模式

## 15.1 巨型 SKILL.md

所有能力、平台、角色與例外都塞入同一文件。

結果：

- 無法導航；
- 全量載入；
- 修改風險高；
- 規則互相污染。

## 15.2 偽模組化

雖然分成多個資料夾，但所有 TMS 彼此直接引用，或必須共同載入才能工作。

這只是把單體拆成多個檔案，並未形成真正子集。

## 15.3 所有能力都列為 SMS

若任何能力都被視為核心，便無法按需載入，也無法安全替換。

## 15.4 FMS 可執行化

將具體流程、工具參數與領域細節塞入 FMS，最終使總導航層失去簡潔性。

## 15.5 權限只靠自然語言提醒

例如：

```text
請不要刪除正式資料。
```

若工具仍允許任意刪除，這不是真正契約，只是期望。

## 15.6 Agent 自我提出、自我修改、自我批准

同一 Agent：

1. 發現問題；
2. 提出修正；
3. 執行修正；
4. 宣稱修正成功；
5. 批准正式發布。

這形成自我驗證閉環，必須透過角色與權限分離打破。

## 15.7 無 DMS 的黑箱完成

系統只回覆「完成」，卻沒有驗證、產物位置、修改摘要、風險資訊與未完成事項。

---

# 第十六章　與 EML、SCL、HVSL 等方法的關係

## 16.1 MSSP 與 EML

MSSP 負責：

- 架構分層；
- 能力定位；
- 子集管理；
- 系統導航。

EML 可負責：

- 高密度語義表達；
- 能力契約；
- 模組標記；
- 依賴聲明；
- 機器可讀的架構描述。

兩者可協同，但不互相取代。

$$
\mathrm{MSSP}
=
\text{Architecture Organization}
$$

$$
\mathrm{EML}
=
\text{Semantic Expression and Compression}
$$

## 16.2 MSSP 與 SCL

FMS 定義系統是什麼。

SCL 定義系統允許如何被改變。

SMS 定義核心能力如何穩定運作。

TMS 定義專門能力如何擴張。

DMS 定義系統如何被觀測、診斷與呈現。

## 16.3 MSSP 與 HVSL

HVSL 關心 Agent 執行後，使用者實際看得到什麼。

因此 DMS 可將機器狀態轉換為 HVSL 所要求的人類可理解狀態。

```text
工具輸出
→ DMS 診斷
→ HVSL 狀態翻譯
→ 使用者可理解結果
```

---

# 第十七章　通用應用場景

## 17.1 研究 Skill System

FMS 定義研究方法與範圍。

SMS 包含：

- 問題分解；
- 來源評估；
- 引用；
- 證據整合。

TMS 包含：

- 法律研究；
- 醫學研究；
- 數學形式化；
- 文獻計量；
- 特定資料庫適配。

## 17.2 軟體工程 Skill System

SMS 包含：

- 儲存庫理解；
- 變更規劃；
- 測試；
- Diff 審查；
- 版本控制。

TMS 包含：

- GitHub；
- CI 修正；
- 特定框架；
- 特定語言；
- 雲端部署；
- 資料庫遷移。

## 17.3 內容製作 Skill System

SMS 包含：

- 來源整理；
- 大綱；
- 語氣；
- 品質檢查；
- 版本管理。

TMS 包含：

- 論文；
- 簡報；
- 社群貼文；
- 影片腳本；
- 多語翻譯；
- 品牌適配。

## 17.4 世界工程 Skill System

SMS 可包含世界理解、世界資料模型、規則驗證、版本與存檔、世界編譯。

TMS 可包含不同遊戲引擎、AI GM、AI 玩家、特定戰鬥或經濟系統，以及特定世界來源。

本文暫不展開此專用架構，留待後續獨立 Skill 文件。

---

# 第十八章　建置路線

## Phase 0：能力盤點

列出現有任務、提示、工具、輸出、權限、失敗案例與重複規則。

## Phase 1：建立 FMS

完成系統敘事、範圍、非目標、能力索引與基礎架構圖。

## Phase 2：識別 SMS 與 TMS

使用兩個問題：

1. 移除後，核心任務還能否閉環？
2. 是否能在最小核心下獨立測試？

## Phase 3：建立 SCL

將工具權限、資料邊界、風險等級、人工批准、設定與成本限制轉換為契約。

## Phase 4：建立 Router

從規則式路由開始：

```text
任務類型
+ 目標平台
+ 輸入格式
+ 風險
→ 載入模組
```

不必一開始使用複雜 AI 路由。

## Phase 5：建立 DMS 與測試

讓每次執行都能回答：

- 載入了什麼；
- 為何載入；
- 執行了什麼；
- 驗證結果；
- 是否越權；
- 是否完成。

## Phase 6：持續演化

依實際任務增加 TMS，而不是預先建立大量空白模組。

---

# 第十九章　評估指標

## 19.1 認知可理解性

- 新維護者定位能力所需時間；
- FMS 是否能在五分鐘內說清楚；
- 架構圖主要元素數；
- 模組責任是否單一。

## 19.2 上下文效率

$$
E_C
=
\frac{
\text{任務有效上下文}
}{
\text{總載入上下文}
}
$$

## 19.3 模組獨立性

- TMS 孤島測試成功率；
- 跨 TMS 直接依賴數；
- 隱藏依賴數；
- 替換單一 TMS 所需修改範圍。

## 19.4 路由品質

- 正確載入率；
- 過度載入率；
- 漏載入率；
- 路由延遲；
- 路由解釋能力。

## 19.5 治理品質

- 未授權操作攔截率；
- 高風險操作批准覆蓋率；
- 變更可追蹤率；
- 回滾成功率；
- 設定遷移成功率。

## 19.6 交付品質

- 任務成功率；
- 驗證通過率；
- 產物可訪問率；
- 使用者可理解狀態覆蓋率；
- 回歸錯誤率。

---

# 第二十章　更深層的理論意義

## 20.1 Skill 是一種可執行知識架構

大型 Skill 不只是知識庫，也不是單純程式。

它同時包含知識、能力、權限、工具、流程、觀測、版本與治理。

因此可以定義：

$$
\mathrm{SkillSystem}
=
\mathrm{Knowledge}
+
\mathrm{Capability}
+
\mathrm{Contract}
+
\mathrm{Execution}
+
\mathrm{Observation}
$$

## 20.2 MSSP 是 Agent 的認知外骨骼

對人類而言，MSSP 降低系統理解成本。

對 Agent 而言，MSSP 降低：

- 上下文噪音；
- 無關規則干擾；
- 路由不確定性；
- 權限誤判；
- 子能力混淆；
- 長期維護漂移。

因此，MSSP 不只是軟體目錄，也是一種 Agent 認知調度結構。

## 20.3 從程式模組化走向能力模組化

傳統模組化關心程式碼如何拆分。

MSSP-Scale Skill 關心：

> 一個智能系統的能力應如何被拆分、載入、授權、測試與組合。

這是一種比程式碼模組更高層的能力模組化。

## 20.4 上下文成為運算資源

在 Agent 系統中，上下文不是無限免費的背景，而是：

- 有容量；
- 有成本；
- 有注意力競爭；
- 有污染風險；
- 有載入延遲；
- 有版本一致性問題。

MSSP-Scale Skill 將上下文從被動文本提升為可調度資源。

---

# 第二十一章　待研究問題

1. 如何自動判定某能力應屬 SMS 或 TMS？
2. Router 應採規則式、模型式還是混合式？
3. 如何形式驗證 TMS 不存在隱藏依賴？
4. 如何測量上下文污染？
5. 如何在多 Agent 間共享 FMS，而隔離 SCL 權限？
6. 如何建立 Skill 的供應鏈安全？
7. 如何簽署與驗證第三方 TMS？
8. 如何讓 Skill 自動產生架構圖，但不把圖當作真實架構的替代品？
9. 如何處理跨 Skill System 的能力組合？
10. EML 是否可成為 MSSP Skill 契約的高密度表示語言？
11. 是否需要原生支援 MSSP 深度與依賴的 Skill Runtime？
12. 如何在保持可演化性的同時，避免模組無限細碎化？

---

# 第二十二章　結論

本文提出 MSSP-Scale Skill，將母集與子集範式從軟體架構方法推進為大型 AI Agent 技能系統的通用組織方法。

其核心結構為：

```text
FMS：技能系統是什麼
SCL：技能系統允許如何被改變與操作
SMS：不可缺少的核心能力
TMS：按需載入的專門能力
DMS：系統如何被觀測、診斷與呈現
Router：任務如何選擇能力與上下文
Runtime：工具如何真正執行
```

MSSP-Scale Skill 的根本目的，不是把一份 Skill 文件拆成更多資料夾，而是重新定義大型技能系統的存在形式：

> Skill 不再是一段被全部塞入上下文的說明文字，而是一個可被導航、選擇、授權、載入、組合、測試、觀測與演化的能力母集。

它要求：

1. 系統先有本體，再有能力；
2. 能力先有契約，再有執行；
3. 核心能力與專門能力分離；
4. 知識與權限分離；
5. 子能力可以孤島測試；
6. 任務只載入真正需要的上下文；
7. 所有重要操作都可觀測與追蹤；
8. 系統可以在不重寫總 Skill 的情況下持續擴張。

因此，MSSP-Scale Skill 可以被視為 AI Agent 時代的一種新型架構單位：

> 它不是單一技能，而是技能的母集；不是單一工作流，而是工作流得以安全組合的能力憲法；不是更長的提示，而是智能系統的認知外骨骼。

後續可以在此通用方法之上，正式建立 MUD 世界工程專用的 MSSP Skill System。

---

# 附錄 A　最小 MSSP-Scale Skill Manifest

```yaml
system:
  id: example-skill-system
  version: 0.1.0
  purpose: 提供範例領域的完整 Agent 能力

fms:
  narrative: FMS/00_SYSTEM_NARRATIVE.md
  capability_index: FMS/03_CAPABILITY_INDEX.yaml

scl:
  permissions: SCL/permissions.policy.yaml
  risks: SCL/risk-levels.yaml
  tools: SCL/tool-access.yaml

sms:
  - id: intent-routing
    path: SMS/intent-routing
  - id: validation
    path: SMS/validation
  - id: result-assembly
    path: SMS/result-assembly

tms:
  - id: adapter-x
    path: TMS/adapters/adapter-x
    activate_when:
      target: x

dms:
  tracing: DMS/tracing
  reports: DMS/reports
```

---

# 附錄 B　TMS 契約模板

```yaml
id:
name:
version:
layer: TMS

purpose:

activate_when:

inputs:

outputs:

requires:
  sms: []
  tools: []
  data: []

permissions:
  may: []
  may_not: []

risk_level:

failure_modes:

validation:

tests:

compatibility:

maintainer:
```

---

# 附錄 C　孤島測試清單

- [ ] TMS 是否可在最小 Runtime 中啟動？
- [ ] 是否只依賴已聲明 SMS？
- [ ] 是否存在未聲明工具依賴？
- [ ] 是否存在其他 TMS 的直接引用？
- [ ] 輸入是否符合契約？
- [ ] 輸出是否可被核心系統接收？
- [ ] 權限拒絕是否正確？
- [ ] 外部工具失敗時是否安全退出？
- [ ] 是否留下可讀診斷？
- [ ] 是否可被替換而不修改 FMS？
- [ ] 是否有版本相容聲明？
- [ ] 是否通過代表任務？

---

# 附錄 D　資料庫理論依據

本文建立於既有 MSSP、SCL 與 EML 系列文件之上，主要延伸關係如下：

1. 《MSSP：母集與子集範式——可視化驅動的軟體架構方法論》
   - 提出 FMS、SMS、TMS 三層認知架構；
   - 將 FMS 定義為純元資料與系統憲法；
   - 提出視覺驅動、文檔即架構與孤島測試。

2. 《設定契約層（SCL）：軟體系統可控制性邊界的先行架構方法論》
   - 將 SCL 定義為 FMS 與 SMS／TMS 之間的可變性介面；
   - 區分系統「能做什麼」與「允許如何被改變」。

3. 《高效新語言（EML）1.5：語意附加驅動的程式設計範式革新》
   - 將 EML 與 MSSP 定義為可協同但彼此獨立的方法；
   - 提出以 EML 壓縮、標記與表達 MSSP 結構的可能性。

本文的新增貢獻，是將上述方法正式映射到 Agent Skill、上下文工程、能力調度與權限治理。
