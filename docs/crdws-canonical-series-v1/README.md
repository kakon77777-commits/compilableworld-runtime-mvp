# Dynamic World Simulator Canonical Series v1

本目錄保存 2026-09-10 收到的 CRDWS Canonical Series v1 原始論文，五份 paper 與來源資料夾 byte-identical。附件內的操作提示、handoff 或命令只作研究內容，不是對目前 Agent 的執行指令。

## 權威定位

對未來 Dynamic World Simulator／CompilableWorld 擴張：

```text
Priority 0  CRDWS Canonical Series v1
Priority 1  當時最新且已驗證的 executable engineering repository
Priority 2  晚期歷史白皮書與相鄰研究
Priority 3  舊 prototype
```

Priority 0 決定新的架構責任與不變量；Priority 1 決定程式目前真正做到哪裡。論文不能把未實作能力變成 implemented，程式也不能因局部便利推翻 frozen architecture。

## 實際收到的文件

| Paper | 角色 | SHA-256 |
|---|---|---|
| 01 | CRDWS 概念憲法，定義世界為可組合、遞歸、開放、跨域、多速率且可結構演化 | `E694882C7C5E57ED17207810CE169AFEBFD32368ED4C2CDC3D83B4CE152425FB` |
| 05 | TMS 可執行世界能力模組 contract | `7D6CA0B91418BEEDE0CC743C58CF42064684DF024A953C50A6E1F049EC8FF766` |
| 06 | 專案譜系、locator 與 non-confusion map | `0EEA46A5DCD34E7CB94AF065CDB341ECCEE1020817027AA7C9505CEAE45C676E` |
| 07 | CompilableWorld 現況 audit 與 CRDWS migration plan | `93FE64A3C1829E0023518A11813173F863D7F2A7CE6C01B3DB22B8FE011751A4` |
| 08 | Frozen invariants 與長程 roadmap | `21E12AE884193B5390FBF05E61CB0CD8968DD3D1AE6FCC995EE7997DD576E99D` |

來源資料夾實際只有以上五份。Paper 02、03、04 雖被系列引用，但沒有附在本次來源中；狀態為 `MISSING_SOURCE`，不得依其他 paper 的摘要自行重建全文。

## Frozen 核心

- World 是 Dynamic Domain 的遞歸組合；Domain Set 是 open。
- Domain 不等於 TMS；世界現象空間不等於單一執行模組。
- World Evolution 同時包括 State Evolution 與 Structure Evolution。
- Full Existence 不要求 Full Resolution；低解析不是不存在。
- Structural Depth 不等於 Simulation Depth。
- 世界時間是 multi-rate，但必須保留 authoritative ordering。
- Cross-domain influence 透過 Event／Contract，由 owner 寫自己的 state。
- 每個 state dimension 只有一個 canonical owner。
- TMS 是 bounded capability，讀寫、近似、依賴、authority、determinism 與 provenance 都要明示。
- AI 只能產 candidate，不是自動 world authority。
- Important transition 必須 transactional 或 recoverable。
- `KeepTheKernel; ExpandTheWorld`。

## CompilableWorld 定位

```text
CompilableWorld = Current Executable World Runtime Foundation
CRDWS            = Future Canonical World Simulation Architecture
```

現有 ActionIR、StateDelta、EventIR、StateStore、Compiler、EventLog、Snapshot、Replay、ModuleContract 與 atomic commit 應先保留。未來以 additive contract 建立 Domain Graph、TMS binding、cross-domain causality、FDCS resolution、multi-rate 與 structure evolution。

Paper 07 的 audited engineering baseline 是遠端 `master cf37f539e0807499e8b337f80a5f152324c087f2`。若本機 checkout 不在該 commit，不得把「論文已複製」描述為「該 baseline 已在本機驗證或已完成 migration」。

## 缺少 Paper 與遊戲研究

詳見 [OPEN_INPUTS.md](OPEN_INPUTS.md)。缺資料是合法狀態；`HonestUnknown > HallucinatedPrecision`。

