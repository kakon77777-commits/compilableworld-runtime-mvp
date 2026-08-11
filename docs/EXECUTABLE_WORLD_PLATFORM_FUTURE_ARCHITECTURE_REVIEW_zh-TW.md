# Executable World Platform 未來架構整合評註

- **評註版本：** v0.1
- **評註日期：** 2026-08-11
- **評註對象：** [`whitepapers/10-compilableworld-executable-world-platform-v0.1-zh-TW.md`](whitepapers/10-compilableworld-executable-world-platform-v0.1-zh-TW.md)
- **外部來源：** `C:\Users\kakon\Downloads\CompilableWorld_Executable_World_Platform_Technical_Whitepaper_v0.1_zh-TW.md`
- **外部來源 SHA-256：** `C60667C31D8AEAA36D1C2C2EB84CBC83B835654C82917EA4FEBA64178FDF1F94`
- **狀態：** non-normative future architecture proposal

## 1. 採納邊界

本白皮書是一份長期架構方向，不是目前 Runtime Package、StateIR、MCP、Snapshot、Replay 或部署契約。它不會自動建立 WGBP、Engine Adapter、Module Registry、多時鐘、Runtime-as-a-Service 或 Direct Renderer，也不會改變既有工作包的完成狀態與優先順序。

若白皮書與現行程式或契約不同，以 `AGENTS.md`、版本化 schema、Compiler、Runtime tests、`CONTRACT_INVENTORY.md` 與 `RUNTIME_CAPABILITY_MATRIX.md` 為準。任何採納都必須另立版本化工作包，依 Authoring／Schema → Compiler → Runtime → Projection／Adapter → Scenario／Replay tests 的順序落地。

白皮書原文在匯入時只做 UTF-8／LF、Markdown 尾端空白與結尾換行正規化；除這些排版字元外，文字內容與外部來源相同。所有評論保留在本文件，避免把後續判斷寫回原稿後失去來源區分。

## 2. 整體判定

方向正確，且與現行 Runtime 的主要不變量相容：

- `World != Engine`，世界語義與呈現／物理層分離；
- 所有玩家、Engine、AI 與 MCP 輸入都必須進入受驗證的 Action boundary；
- Runtime State 只能由 Module 產生 StateDelta，再由 Kernel 原子提交；
- Projection、Narrative、Memory 與 Engine Object 都不能冒充世界真相；
- WorldEntity identity 與短生命週期 Engine instance 分離；
- AI 是 authoring／proposal／runtime actor，不是隱形 StateStore owner；
- Same World／Multiple Presentation 是合理的長期驗證目標；
- sidecar-first 與 FakeEngine-first 能維持引擎獨立性與測試性。

因此這份白皮書適合保留為平台化方向，但 WGBP 尚不能直接照範例實作；以下問題必須先轉成正式契約。

## 3. 實作前必須修正的問題

| 等級 | 問題 | 風險 | 必要修正 |
|---|---|---|---|
| Blocker | `authority = negotiated` 沒有 ownership protocol | World 與 Engine 可能同時寫 HP、Position 或 Combat，形成 split-brain／double commit | 每一 canonical path 在任一 epoch 只能有一個 writer；若交給 subsystem，必須有 lease、fencing token、期限、撤銷、handoff barrier 與 crash recovery。Mirrored state 只能是衍生副本，不能雙主。 |
| Blocker | `EngineEvent` 範例太接近可直接注入 EventIR | 未授權 Client 可偽造命中、死亡或世界事實 | 對外名稱應先是 `EngineReport`／`SubsystemObservation`；驗證 client、permission、binding generation、authority lease、sequence、idempotency 與 payload 後，才由正式 Module 產生 StateDelta／EventIR。 |
| Blocker | Save Barrier 只有概念順序，沒有失敗協定 | Runtime、EventLog 與 Engine shared state 可能得到彼此不一致的存檔 | 定義 `barrier_id`、participant、prepare／commit／abort、deadline、epoch、checksum、last committed sequence、重啟恢復與 partial participant failure。現有 Snapshot／journal／outbox 不等於跨程序 ACID。 |
| High | 範例 ID `npc:000000004211` 不符合現行 ID grammar | 現有 schema 使用 `^[a-z][a-z0-9_.-]*$`，冒號 ID 會編譯失敗 | WGBP v0.1 優先沿用 `npc.000000004211`；若一定要冒號，必須另做全域 ID migration、escaping 與 cross-schema compatibility。 |
| High | `EngineIntent` 使用 `actor`／`target`，事件名稱也與現行契約不同 | Adapter 作者可能誤以為這些就是 ActionIR／EventIR 的正式欄位 | 明確標示例子是 adapter DTO；正式轉換後使用當時版本的 `actor_id`、`target_id`、`args` 與既有 EventIR registry。白皮書中的 `character.moved`、`combat.damage` 等目前只是未採納例名。 |
| High | `EntityBinding=(WorldEntityId, EngineInstanceId, Generation)` 身份不足 | 重連、多 Client、多 timeline 或場景重建時仍可能接受 stale instance | 至少加入 `runtime_instance_id`、`timeline_id`、`client_id`、`binding_id`、`subscription_id`、`generation`、`issued_at`、`expires_at`；具寫入權時再帶 authority epoch／fencing token。 |
| High | Projection Snapshot／Delta 只有單一 `generation` | 封包遺失、亂序、重連、跨 scope 或權限變更時無法安全續接 | 加入 versioned projection contract、subscription ID、snapshot ID、base sequence、next sequence、runtime tick/state version、visibility scope、checksum、ACK／resume token；gap 或 hash mismatch 必須要求完整 resync。 |
| High | Multi-rate clocks 未定義跨 clock 因果與 replay | render/gameplay/world clock 漂移會改變事件順序，跨引擎結果不可重現 | Runtime 只保留一個 canonical ordering domain；其他 clock 以明確 domain、ratio、epoch 與 recorded input 映射。Renderer 不得推進 world tick。Snapshot 必須保存 clock-domain state，Replay 以 canonical order 為準。 |
| High | Hydration／Dehydration 說「commit semantic deltas」但未限制寫入面 | Engine 可能在卸載場景時批次回寫任意世界狀態 | 只能提交已授權 ActionIR 或 EngineReport，經 Module 驗證後提交；dehydrate 需要 binding freeze、final sequence、ACK、timeout 與 stale-generation rejection。 |
| High | Projection 被描述成決定權限與可用 Action | UI 不顯示操作不能構成安全授權，投影資料也可能外洩秘密 | ACL／Session／ModuleContract／Action validation 才是 authority；Projection 只能輸出經過 actor/session visibility filter 的可見能力提示，Server 仍需獨立重驗。 |
| Medium | `SemanticPosition -> PhysicalPosition` 被寫成單純函數 | 一個語義地點可能有多張地圖、入口、spawn anchor、LOD 與 map version | Mapping 應由 Presentation Package／Adapter 擁有，輸入還需 scene/map version、archetype、anchor policy 與 deterministic seed；輸出不是 canonical world fact。 |
| Medium | Module Dependency Graph 提議拒絕所有 cycle | Build dependency cycle 與 Event reaction loop 不是同一問題 | 編譯依賴應是 DAG；Runtime event graph 可以有受限回饋，但需 reaction budget、causation depth、loop detection 與 transaction boundary。 |
| Medium | Same World／Two Engines 缺少等價判定 | 只說「結果一致」不足以處理不同 FPS、physics 與浮點差異 | 定義 canonical world hash，固定 initial package、snapshot、RNG streams、ordered semantic inputs 與 clock mapping；比較 canonical state/event outcome，不比較 animation／physics frame。 |
| Medium | 跨語言數值與亂數規則不足 | Python、Godot、Bakin 或 Renderer 可能因 float／rounding／random 不同而分歧 | Canonical 規則只使用已版本化 FunctionIR／RNG service，規定 finite number、rounding、seed stream、serialization 與 hash normalization；Engine random 只能影響 presentation，除非以輸入證據提交。 |
| Medium | Runtime-as-a-Service 與多 Client 被描述為自然延伸 | 現有 Runtime 仍有 single-process／single-world 與 distributed consensus 邊界 | 必須先完成 authoritative runtime ownership、distributed idempotency、projection isolation、backpressure、audit anchor 與 external supervision，不能由 WGBP transport 宣告取代。 |

## 4. 建議的 WGBP 最小信封

第一版不要讓 Adapter 自行拼接裸欄位。至少應有四類版本化信封：

### 4.1 Session／Capability

```text
contract_version
runtime_instance_id
timeline_id
session_id
client_id
actor_id
permissions
capabilities
opened_at / expires_at
```

### 4.2 Entity Binding

```text
binding_id
runtime_instance_id
timeline_id
client_id
subscription_id
world_entity_id
engine_instance_id
generation
authority_epoch / fencing_token (only when delegated)
issued_at / expires_at
```

### 4.3 Engine Intent／Report

```text
contract_version
session_id
client_request_id
idempotency_key
binding_id / generation
engine_sequence
correlation_id / causation_id
intent_or_report_type
payload
```

Intent 轉成 ActionIR；Report 先進入具 ModuleContract 的 validator。兩者都不能自行成為 committed EventIR。

### 4.4 Projection Stream

```text
projection_contract
subscription_id
snapshot_id
base_sequence
sequence
runtime_tick / state_version
visibility_scope
changes
checksum
resume_token
```

任何 sequence gap、subscription mismatch、stale generation、visibility change 或 checksum mismatch 都 fail closed 並要求新 Snapshot。

## 5. 不影響現行計畫的採納順序

### P0 — 文件保存（本輪）

- 保存原始白皮書與 SHA-256；
- 登記為 non-normative future proposal；
- 記錄問題與採納 gate；
- 不修改 Runtime、Schema、Snapshot 或既有工作包順序。

### P1 — CW-WGBP-00 Contract-only

- 先寫 `ENGINE_BINDING_CONTRACT_zh-TW.md`；
- 建立 capability、session、binding、intent/report、projection snapshot/delta schema；
- 使用 FakeEngine client；
- 驗證 Terminal／Web／FakeEngine 對同一 semantic input 產生相同 canonical world hash。

### P2 — Binding／Projection

- 實作 generation／stale rejection；
- snapshot／delta／ACK／resync；
- per-session visibility 與 backpressure；
- hydrate／dehydrate crash tests。

### P3 — Clock／Save Barrier

- 版本化 clock domains；
- deterministic clock mapping；
- prepare／commit／abort save barrier；
- restart、timeout、partial failure 與 replay tests。

### P4 — 真實 Adapter

- FakeEngine 全部驗收通過後，再選 Bakin 或 Godot；
- Adapter 不得帶入第二套 quest／economy／relationship rules；
- Direct Renderer 保留為後續 Presentation experiment，不作為 Runtime 成功的前置條件。

## 6. 結論

白皮書的核心抽象沒有問題：CompilableWorld 可以長期演化成「可執行世界平台」，而不是綁定某一個 Game Engine。但真正困難的部分不是 Renderer API，而是跨程序 authority、identity、ordering、idempotency、visibility、save barrier 與 replay equivalence。

所以建議採納其方向，不直接採納尚未版本化的範例欄位。第一個新里程碑應維持白皮書提出的 CW-WGBP-00，但把它收斂為 Contract-only + FakeEngine + canonical world hash，不立即改寫現有 Runtime 或接真實引擎。
